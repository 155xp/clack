# Clack website

The public site is a static build generated from the handbook in `docs/` and the language examples. Run `npm ci` and `npm run build` from the repository root. The output is `website/dist/`.

`config.json` holds the canonical site URL, GitHub repository, branch, and displayed version. The generator reads that file on each build. All pages use the same navigation, assets, heading links, and local search index. Search runs in the browser and needs no service or credentials.

Markdown documentation remains the source of truth. Relative documentation links become website routes; links to compiler and example files open their corresponding GitHub source. The download button links to GitHub's source archive, so clean deployments work without ignored build artifacts. The existing source ZIP, when available at `build/clack-0.1.0-source.zip`, is also copied to `downloads/clack-source.zip`.

The site needs no server runtime or environment secrets. Vercel can run the root build command and publish `website/dist`.
