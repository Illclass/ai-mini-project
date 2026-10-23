import catalog from './catalog.json' with { type: 'json' }
import contract from './contract.json' with { type: 'json' }
import { chemicalNames } from '../locales/scope.js'
export { catalog }
export const availableProducts = catalog.products.filter(item => item.product_id && item.doc_id && item.title)
export const availableEquipment = catalog.equipment.filter(item => item.coverage !== 'none' && item.product_ids.some(id => availableProducts.some(product => product.product_id === id)))
export const equipmentFor = id => availableEquipment.find(item => item.equipment_id === id)
export function productsFor(equipmentId) {
 const equipment = equipmentFor(equipmentId)
 return equipment ? availableProducts.filter(item => equipment.product_ids.includes(item.product_id)) : equipmentId ? [] : availableProducts
}
export function normalizeScope(equipmentId, productId) {
 if(equipmentId && !equipmentFor(equipmentId)) return { equipment_id:null, product_id:null }
 const equipment_id = equipmentFor(equipmentId)?.equipment_id || null
 const product_id = productsFor(equipment_id).find(item => item.product_id === productId)?.product_id || null
 return { equipment_id, product_id }
}
export function requestScope(topic, equipmentId, productId) {
 return topic === contract.topics.chemical ? normalizeScope(equipmentId, productId) : { equipment_id:null, product_id:null }
}
export function productLabel(item, language) {
 const index = ['zh','vi','en','km'].indexOf(language)
 return `${index < 0 ? item.name : chemicalNames[item.product_id]?.[index] || item.name} · ${item.product_id}`
}
export function equipmentLabel(item, language, demo) {
 const names = { metal:'PVD / Plating', solvent:'Solvent cleaning', utility:'Neutralization / Scrubber' }
 const name = language === 'ko' ? item.name.replace(' (가상)', '') : names[item.process] || item.name.replace(' (가상)', '')
 return `${name} · ${demo}`
}
