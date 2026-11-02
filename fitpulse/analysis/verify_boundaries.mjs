// Synthetic boundary cases exercise the actual clean-layer SQL in an isolated database.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { utcTextParsers } from './pg_parsers.mjs';
const { PGlite } = await import(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const db=new PGlite({parsers:utcTextParsers});
const checks=[];
const check=(name,condition)=>{if(!condition)throw new Error(name);checks.push(name);};
try {
  await db.exec(await fs.readFile(path.join(ROOT,'sql/00_schema.sql'),'utf8'));
  await db.exec(`
    INSERT INTO raw.users VALUES
      ('edge','2026-08-01 12:00','android','UA','organic','A'),
      ('ios','2026-08-01 12:00','ios','UA','organic','B'),
      ('mature','2026-08-24 00:00','android','UA','organic','A'),
      ('immature','2026-08-24 00:00:01','android','UA','organic','B'),
      ('qa','2026-08-01 12:00','android','UA','internal','A');
    INSERT INTO raw.events VALUES
      (1,'edge','session_start','2026-07-31 12:00:30'),
      (1,'edge','session_start','2026-07-31 12:00:30'),
      (2,'edge','session_start','2026-07-31 12:00:31'),
      (3,'edge','trial_start','2026-07-31 12:00:30'),
      (4,'edge','onboarding_complete','2026-08-02 12:00'),
      (5,'edge','session_start','2026-08-02 12:00'),
      (6,'ios','session_start','2026-08-03 12:00'),
      (7,'edge','trial_start','2026-08-08 12:00'),
      (8,'edge','session_start','2026-08-08 12:00'),
      (9,'edge','session_start','2026-10-01 00:00'),
      (10,'ios','session_start','2026-07-31 12:00:30'),
      (11,'immature','session_start','2026-09-30 23:59:59'),
      (12,'qa','session_start','2026-08-01 12:00'),
      (13,'ios','trial_start','2026-08-08 11:59:59'),
      (14,'ios','session_start','2026-08-15 12:00');
    INSERT INTO raw.payments VALUES
      (1,'edge','2026-08-02 12:00','monthly','purchase',0),
      (2,'edge','2026-08-15 12:00','monthly','purchase',12.99),
      (3,'edge','2026-08-31 12:00','monthly','renewal',12.99),
      (4,'edge','2026-09-01 12:00','monthly','refund',-12.99),
      (5,'edge','2026-09-08 12:00','monthly','renewal',12.99),
      (6,'edge','2026-10-01 00:00','monthly','renewal',12.99),
      (7,'edge','2026-08-01 11:59:59','monthly','purchase',12.99),
      (8,'ios','2026-08-15 11:59:59','monthly','purchase',12.99),
      (9,'mature','2026-09-30 23:59:59','monthly','purchase',12.99),
      (10,'qa','2026-08-02 12:00','monthly','purchase',12.99);
  `);
  await db.exec(await fs.readFile(path.join(ROOT,'sql/01_clean.sql'),'utf8'));
  const users=Object.fromEntries((await db.query('SELECT * FROM an.user_facts')).rows.map(r=>[r.user_id,r]));
  const events=(await db.query('SELECT * FROM an.events ORDER BY event_id')).rows;
  const ids=events.map(r=>Number(r.event_id));
  check('internal user excluded',!users.qa&&Object.keys(users).length===4);
  check('exact offset repaired and duplicate removed',ids.filter(x=>x===1).length===1&&events.find(r=>Number(r.event_id)===1).event_ts==='2026-08-01 12:00:30');
  check('near offset not repaired',!ids.includes(2));
  check('other event type not repaired',!ids.includes(3));
  check('iOS offset not repaired',!ids.includes(10));
  check('activity cutoff is exclusive',!ids.includes(9)&&ids.includes(11));
  check('24h onboarding boundary is exclusive',users.edge.onboarded&&!users.edge.onboarded_24h);
  check('D1 includes 24h and excludes 48h',users.edge.active_d1&&!users.ios.active_d1);
  check('trial excludes day 7',!users.edge.started_trial&&users.ios.started_trial);
  check('W1 includes day 7 and excludes day 14',users.edge.active_w1&&!users.ios.active_w1);
  check('D14 excludes exact day 14 and zero purchase',!users.edge.is_payer&&users.ios.is_payer);
  check('D30 excludes exact day 30',Math.abs(Number(users.edge.revenue_30d)-12.99)<1e-9);
  check('D38 excludes exact day 38 and keeps signed refund',Math.abs(Number(users.edge.revenue_38d)-12.99)<1e-9&&users.edge.refunded_38d);
  check('D38 maturity includes equality at cutoff',users.mature.mature_38d&&Math.abs(Number(users.mature.revenue_38d)-12.99)<1e-9);
  check('D38 immature values stay NULL',!users.immature.mature_38d&&users.immature.revenue_38d===null&&users.immature.refunded_38d===null);
  const payments=(await db.query('SELECT payment_id FROM an.payments')).rows.map(r=>r.payment_id);
  check('payment cutoff, pre-signup and QA excluded',[6,7,10].every(id=>!payments.includes(id))&&payments.length===7);
  await fs.mkdir(path.join(ROOT,'output'),{recursive:true});
  await fs.writeFile(path.join(ROOT,'output/boundary_verification.json'),JSON.stringify({status:'PASS',checks_passed:checks.length,checks},null,2));
  console.log('PASS:',checks.length,'SQL boundary checks');
} finally {await db.close();}
