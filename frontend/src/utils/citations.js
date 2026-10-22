/** Select available sources explicitly cited in an answer, in citation order. */
export function getCitedSources(content = '', sources = []) {
  const byId = new Map(sources.map(source => [source.id, source]))
  const selected = []
  const seen = new Set()
  const groups = content.matchAll(/\[\s*(S\d+(?:\s*[,，、;；]\s*S\d+)*)\s*\]/g)

  for (const group of groups) {
    for (const [id] of group[1].matchAll(/S\d+/g)) {
      if (byId.has(id) && !seen.has(id)) {
        selected.push(byId.get(id))
        seen.add(id)
      }
    }
  }
  return selected
}
