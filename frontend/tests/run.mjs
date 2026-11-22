import ts from 'typescript';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
mkdirSync('.test-build',{recursive:true});
for(const name of ['DeviceActivity','identification','vendorRegistry','workspace','PortTelemetry','PortsView','FirewallView','DHCPView','AddonNav']){
 const source=readFileSync(`src/${name}.tsx`,'utf8');
 const result=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 writeFileSync(`.test-build/${name}.mjs`,result.replace(/(['"])\.\/(DeviceActivity|identification|vendorRegistry|workspace|PortTelemetry|PortsView|FirewallView|DHCPView|AddonNav)\1/g,'$1./$2.mjs$1'));
}
const result=spawnSync(process.execPath,['--test','tests/workspace.test.mjs','tests/addonNav.test.mjs','tests/tokens.test.mjs'],{stdio:'inherit'});
process.exit(result.status??1);
