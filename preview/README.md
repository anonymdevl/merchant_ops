# Login preview

A development harness, not part of the installed app. Nothing here is
served by the site.

Open any of these directly from disk:

  login-preview.html   the real portal.js running against mock settings
  v-split.html         static layout: brand panel left
  v-right.html         static layout: brand panel right
  v-centred.html       static layout: brand as full-screen backdrop

Each one loads `../merchant_ops/public/css/portal.css` and the real
`portal.js` by relative path, so there is a single source of truth. Edit
the stylesheet in `public/`, refresh the browser, and you are looking at
exactly what the site will serve — no `bench build` in the loop.

`login-preview.html` stubs `window.fetch` to return sample branding and
rewrites the path to `/login`, because portal.js only activates on portal
routes. The three `v-*.html` files skip the JS entirely and render the
post-build DOM directly, which is useful for comparing layouts side by
side.

Delete this folder if you would rather not ship it. Nothing imports it.
