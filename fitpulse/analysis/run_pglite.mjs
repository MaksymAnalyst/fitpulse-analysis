// Isolated PostgreSQL (WASM) alternative; writes the same CSVs as run_sql.py.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { utcTextParsers } from './pg_parsers.mjs';
const { PGlite } = await import(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const OUT=path.join(ROOT,'output');
await fs.mkdir(OUT,{recursive:true});
const db=new PGlite({parsers:utcTextParsers});
function parseCsv(text) {
  const rows=[];let row=[],cell='',quoted=false;
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(c==='"') { if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted; }
    else if(c===','&&!quoted){row.push(cell);cell='';}
    else if(c==='\n'&&!quoted){row.push(cell.replace(/\r$/,''));rows.push(row);row=[];cell='';}
    else cell+=c;
  }
  if(cell||row.length){row.push(cell.replace(/\r$/,''));rows.push(row);}
  if(quoted) throw new Error('Unclosed CSV quote');
  return rows;
}
const lit=v=>v===''?'NULL':"'"+v.replaceAll("'","''")+"'";
const csv=v=>{const s=v==null?'':v instanceof Date?v.toISOString().replace('T',' ').replace('.000Z',''):String(v);return /[,"\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;};
try {
  const version=(await db.query('SELECT version() AS version')).rows[0].version;
  await db.exec(await fs.readFile(path.join(ROOT,'sql/00_schema.sql'),'utf8'));
  for(const name of ['users','events','payments','marketing_spend']) {
    const [header,...rows]=parseCsv(await fs.readFile(path.join(ROOT,'data',name+'.csv'),'utf8'));
    for(let i=0;i<rows.length;i+=500) {
      const batch=rows.slice(i,i+500);
      if(batch.some(row=>row.length!==header.length)) throw new Error('CSV width: '+name);
      await db.exec(`INSERT INTO raw.${name} VALUES ${batch.map(r=>'('+r.map(lit).join(',')+')').join(',')}`);
    }
    console.log('loaded',name,rows.length);
  }
  let count=0;
  for(const name of (await fs.readdir(path.join(ROOT,'sql'))).filter(n=>n.endsWith('.sql')&&!n.startsWith('00')).sort()) {
    const sql=await fs.readFile(path.join(ROOT,'sql',name),'utf8');
    const parts=sql.split(/^-- name:\s*(\w+)\s*$/m);
    if(parts.length===1) await db.exec(sql);
    for(let i=1;i<parts.length;i+=2) {
      const res=await db.query(parts[i+1]);const cols=res.fields.map(f=>f.name);
      const output=[cols.join(','),...res.rows.map(r=>res.fields.map(f=>
        csv(r[f.name] instanceof Date && f.dataTypeID===1082 ? r[f.name].toISOString().slice(0,10) : r[f.name])
      ).join(','))].join('\n')+'\n';
      await fs.writeFile(path.join(OUT,name.replace('.sql','')+'__'+parts[i]+'.csv'),output);
      console.log(name,parts[i],res.rows.length);count++;
    }
  }
  await fs.writeFile(path.join(OUT,'sql_run_manifest.json'),JSON.stringify({engine:version,result_sets:count},null,2));
} finally {await db.close();}
