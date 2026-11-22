import { loadGlossary, loadLibrary } from './data'
import { parseRoute } from './router'
import { renderCollection } from './screens/collection'
import { renderPlayer } from './screens/player'
import { renderShelf } from './screens/shelf'

const app = document.querySelector<HTMLDivElement>('#app')!
let leave: () => void = () => {}
let gen = 0

async function route() {
  const my = ++gen
  const alive = () => my === gen
  leave(); leave = () => {}
  const r = parseRoute(location.hash)
  let lib
  try { lib = await loadLibrary() } catch (e) {
    app.innerHTML = `<main class="sheet"><p class="empty">The library could not be loaded.</p></main>`
    console.error(e)
    return
  }
  if (!alive()) return
  window.scrollTo(0, 0)
  switch (r.name) {
    case 'shelf': renderShelf(app, lib, 'collections'); break
    case 'index': {
      const g = await loadGlossary().catch((e) => { console.error(e); return undefined })
      if (!alive()) return
      leave = renderShelf(app, lib, 'index', g, r.entry)
      break
    }
    case 'recent': renderShelf(app, lib, 'recent'); break
    case 'collection': renderCollection(app, lib, r.id); break
    case 'piece': {
      const dispose = await renderPlayer(app, lib, r.id, alive)
      if (alive()) leave = dispose; else dispose()
      break
    }
  }
}

addEventListener('hashchange', route)
route()

// offline support and "add to home screen" (production builds only; the dev server must always serve fresh files)
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('./sw.js').catch(() => {}) })
}
