// Bundle the repository originals; no duplicated committed PDFs or backend changes.
const urls = import.meta.glob('../../../rag-service/data/**/*.pdf', { eager: true, query: '?url', import: 'default' })
export function originalUrl(file) { return urls[`../../../rag-service/data/${file}`] || null }
