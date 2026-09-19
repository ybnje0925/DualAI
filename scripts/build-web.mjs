import {mkdir,readFile,writeFile,readdir,copyFile,rm} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const output=path.resolve(root,"web-dist");
if(path.dirname(output)!==root || path.basename(output)!=="web-dist") throw Error("Unsafe output directory");
await rm(output,{recursive:true,force:true});
await mkdir(output,{recursive:true});
for(const name of ["index.html","styles.css","app.js"]) await copyFile(path.join(root,"web",name),path.join(output,name));
const crc32=buffer=>{
 let crc=0xffffffff;
 for(const value of buffer){crc^=value;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}
 return (crc^0xffffffff)>>>0;
};
const local=[],central=[];let offset=0;
const names=(await readdir(path.join(root,"extension"))).sort();
for(const name of names){
 const filename=Buffer.from(name);
 const content=Buffer.from((await readFile(path.join(root,"extension",name),"utf8")).replace(/^\uFEFF/,""));
 const crc=crc32(content), header=Buffer.alloc(30);
 header.writeUInt32LE(0x04034b50);header.writeUInt16LE(20,4);header.writeUInt16LE(0x800,6);header.writeUInt16LE(33,12);
 header.writeUInt32LE(crc,14);header.writeUInt32LE(content.length,18);header.writeUInt32LE(content.length,22);header.writeUInt16LE(filename.length,26);
 const dir=Buffer.alloc(46);
 dir.writeUInt32LE(0x02014b50);dir.writeUInt16LE(20,4);dir.writeUInt16LE(20,6);dir.writeUInt16LE(0x800,8);dir.writeUInt16LE(33,14);
 dir.writeUInt32LE(crc,16);dir.writeUInt32LE(content.length,20);dir.writeUInt32LE(content.length,24);dir.writeUInt16LE(filename.length,28);dir.writeUInt32LE(offset,42);
 local.push(header,filename,content);central.push(dir,filename);offset+=header.length+filename.length+content.length;
}
const directory=Buffer.concat(central),end=Buffer.alloc(22);
end.writeUInt32LE(0x06054b50);end.writeUInt16LE(names.length,8);end.writeUInt16LE(names.length,10);end.writeUInt32LE(directory.length,12);end.writeUInt32LE(offset,16);
await writeFile(path.join(output,"dualai-extension.zip"),Buffer.concat([...local,directory,end]));
console.log("Built static web app + extension ZIP (no Python runtime, no API server)");
