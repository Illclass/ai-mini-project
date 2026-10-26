import {readFileSync,writeFileSync} from 'node:fs'
import {faqRecommendations} from '../src/api/recommendations.js'
import contract from '../src/api/contract.json' with {type:'json'}
const target=new URL('../src/api/candidates.json',import.meta.url)
const text=JSON.stringify(Object.fromEntries(contract.languages.map(language=>[language,{chemical:faqRecommendations(language,contract.topics.chemical),law:faqRecommendations(language,contract.topics.law)}])),null,1)+'\n'
if(process.argv.includes('--check')){
 if(readFileSync(target,'utf8')!==text)throw new Error('Regenerate FAQ: node scripts/generate-recommendations.mjs')
}else writeFileSync(target,text)
