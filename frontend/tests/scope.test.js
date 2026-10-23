import test from 'node:test'
import assert from 'node:assert/strict'
import { catalog, availableEquipment, availableProducts, equipmentFor, productsFor, normalizeScope, requestScope, productLabel, equipmentLabel } from '../src/api/scope.js'
import { scopeCopy } from '../src/locales/scope.js'
import contract from '../src/api/contract.json' with { type:'json' }
import { createApi } from '../src/api/client.js'

test('changing equipment clears incompatible products and allows only linked IDs', () => {
 for (const equipment of availableEquipment) {
  assert.deepEqual(productsFor(equipment.equipment_id).map(p=>p.product_id).sort(), [...equipment.product_ids].sort())
  for (const product of catalog.products) {
   const normalized = normalizeScope(equipment.equipment_id, product.product_id)
   assert.equal(normalized.product_id, equipment.product_ids.includes(product.product_id) ? product.product_id : null)
  }
 }
})
test('unknown IDs are never sent; law requests never carry chemical scope', () => {
 assert.deepEqual(normalizeScope('arbitrary-device','arbitrary-product'),{equipment_id:null,product_id:null})
 assert.deepEqual(requestScope(contract.topics.law,catalog.equipment[0].equipment_id,catalog.products[0].product_id),{equipment_id:null,product_id:null})
 assert.equal(productsFor(null).length,catalog.products.length)
})
test('equipment without documents is excluded and stale selections are cleared; labels exist in all languages', () => {
 for (const equipment of catalog.equipment.filter(e=>e.coverage==='none')) {
  assert(!availableEquipment.includes(equipment))
  assert.equal(equipmentFor(equipment.equipment_id),undefined)
  assert.deepEqual(productsFor(equipment.equipment_id),[])
  assert.deepEqual(normalizeScope(equipment.equipment_id,catalog.products[0].product_id),{equipment_id:null,product_id:null})
 }
 const keys=Object.keys(scopeCopy.ko).sort()
 for (const language of contract.languages) {
  assert.deepEqual(Object.keys(scopeCopy[language]).sort(),keys)
  for(const item of catalog.products) assert(productLabel(item,language).includes(item.product_id))
  for(const item of catalog.equipment) assert(equipmentLabel(item,language,scopeCopy[language].demo).includes(scopeCopy[language].demo))
 }
})
test('equipment/product selection reaches the actual API payload without ID translation', async () => {
 const equipment=catalog.equipment.find(e=>e.product_ids.length)
 const scope=normalizeScope(equipment.equipment_id,equipment.product_ids[0])
 let payload
 const api=createApi(async (_path,options)=>{
  payload=JSON.parse(options.body)
  return new Response(JSON.stringify({answer:'review',sources:[],handoff:true,needs_review:true,latency_ms:1}),{headers:{'Content-Type':'application/json'}})
 })
 await api.ask({question:'작업 전 확인 사항',topic:contract.topics.chemical,language:contract.languages[0],...scope})
 assert.equal(payload.equipment_id,equipment.equipment_id)
 assert.equal(payload.product_id,equipment.product_ids[0])
 assert(equipmentFor(payload.equipment_id))
})

test('selectable equipment and products always have registered source documents',()=>{
 assert(availableEquipment.length>0 && availableProducts.length>0)
 assert(availableEquipment.every(e=>e.coverage!=='none' && productsFor(e.equipment_id).length>0))
 assert(availableProducts.every(p=>p.doc_id && p.title && p.product_id))
})
