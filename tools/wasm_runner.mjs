import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const runtime=path.join(root,'runtime','wasm');
async function load(name,options){const {default:init}=await import(pathToFileURL(path.join(runtime,name+'.js')).href);return init({wasmBinary:fs.readFileSync(path.join(runtime,name+'.wasm')),...options});}
if(process.argv[2]==='compile'){
 const config=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));const output=[];
 const tbPath=config.tb?path.resolve(config.tb):path.join(root,'p6_judge_tb.v');
 const tbName=path.basename(tbPath);const top=config.top||'p6_judge_tb';
 const pre=await load('ivlpp',{print:line=>output.push(line),printErr:console.error});
 const vfs=file=>'/'+path.relative(config.work,file).replaceAll('\\','/');
 for(const file of config.files){const virtual=vfs(file);pre.FS.mkdirTree(path.posix.dirname(virtual));pre.FS.writeFile(virtual,fs.readFileSync(file));}
 pre.FS.writeFile('/'+tbName,fs.readFileSync(tbPath));
 pre.FS.writeFile('/flags.conf',['relative include:true',...config.defines.map(d=>'D:'+d),...config.include.map(d=>'I:'+vfs(d)),''].join('\n'));
 const args=['-L','-F/flags.conf',...config.units.map(vfs),'/'+tbName];
 const status=pre.callMain(args);if(status)process.exit(status);
 const compiler=await load('ivl',{print:console.log,printErr:console.error});
 compiler.FS.writeFile('/ivl.conf',[
  'basedir:/','module:system.vpi','generation:2005','generation:no-specify','out:/out.vvp',
  'iwidth:32','widthcap:65536','functor:cprop','functor:nodangle','flag:DLL=vvp.tgt','root:'+top,''
 ].join('\n'));
 compiler.FS.writeFile('/src.v',output.join('\n')+'\n');
 const result=compiler.callMain(['-C/ivl.conf','--','/src.v']);if(result)process.exit(result);
 fs.writeFileSync(config.output,compiler.FS.readFile('/out.vvp'));
}else if(process.argv[2]==='run'){
 const sim=await load('vvp',{print:console.log,printErr:console.error});
 sim.FS.writeFile('/submission.vvp',fs.readFileSync(process.argv[3]));
 sim.FS.writeFile('/code.txt',fs.readFileSync(process.argv[4]));
 process.exitCode=sim.callMain(['/submission.vvp',...process.argv.slice(5)])||0;
}else{console.error('Use compile CONFIG or run BINARY CODE PLUSARGS');process.exit(2);}
