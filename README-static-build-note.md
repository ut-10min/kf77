# Static build maintenance note

- `npm run build` generates `dist/`.
- `dist/` should not be edited manually.
- GitHub Actions uses `actions/setup-node@v6` with `node-version: lts/*` and `check-latest: true`, so the workflow follows the latest Node.js LTS line automatically.
- The build script uses only Node.js built-in modules and has no npm package dependencies.
- The workflow verifies that `common.js`, `talks.js`, `timetable.js`, and placeholder strings are not left in `dist/`.
