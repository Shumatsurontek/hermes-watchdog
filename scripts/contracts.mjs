import {readFile, writeFile} from 'node:fs/promises';
import {compile} from 'json-schema-to-typescript';
import Ajv from 'ajv';
import standalone from 'ajv/dist/standalone/index.js';
const names = ['WorkPage', 'WorkerDetail', 'HistoryPage', 'ActionResult', 'CancelResult'];
const ajv = new Ajv({code: {source: true, esm: true}, strict: true});
for (const name of names) {
  const schema = JSON.parse(await readFile(`desktop/generated/${name}.schema.json`, 'utf8'));
  // Draft 7 and Pydantic's subset of 2020-12 share these keywords.
  ajv.addSchema(schema);
  await writeFile(`desktop/generated/${name}.d.ts`, await compile(schema, name, {bannerComment: '/* Generated from Python response models. Do not edit. */', maxItems: -1}));
}
await writeFile('desktop/generated/validators.js', standalone(ajv, Object.fromEntries(names.map(n => [`validate${n}`, n]))));
await writeFile('desktop/generated/validators.d.ts', "import type {ValidateFunction} from 'ajv';\n" + names.map(n => `import type {${n}} from './${n}';\nexport const validate${n}: ValidateFunction<${n}>;`).join('\n') + '\n');
