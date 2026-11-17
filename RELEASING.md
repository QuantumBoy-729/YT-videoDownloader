# Releasing

Releases are cut from `main` by pushing a version tag. GitHub Actions then tests,
builds the Python packages and the Windows program, and attaches them to a GitHub
release.

## Before the first release

- **Try the Windows program on a real Windows machine.** CI checks that it starts and
  passes its self-check, but nobody has watched it download a video there.
- **Try a real download** (a YouTube link, and one from another site) from an
  installed copy. The tests use a local server and never touch real sites.
- Consider renaming the GitHub repository from `YT-videoDownloader` to
  `universal-downloader` (Settings, General). GitHub redirects the old name; then
  update the URLs in `README.md` and `pyproject.toml`.
- For PyPI, do the one-time setup below.

## Each release

1. Merge the work into `main` and wait for CI to pass.
2. In `universal_downloader/__init__.py`, set `__version__` (for example `2.0.1`).
3. In `CHANGELOG.md`, change `unreleased` to the date and add anything missing.
4. Commit, then tag and push:

   ```bash
   git commit -am "Release 2.0.1"
   git tag v2.0.1
   git push origin main v2.0.1
   ```

5. CI builds the packages and `UniversalDownloader.exe`, runs the self-check on
   each, and creates the GitHub release with them attached. Edit the release notes
   from the changelog.
6. Check it: install the published package in a clean environment and run
   `universal-downloader --smoke-test`.

The tag must match `__version__`; the job fails if it does not.

## Publishing to PyPI

One-time setup, using PyPI "trusted publishing" so no password is stored:

1. On pypi.org, add a pending publisher (Account, Publishing) with project name
   `universal-downloader`, this repository's owner and name, workflow `ci.yml`, and
   environment `pypi`.
2. In the repository, create an environment named `pypi` (Settings, Environments).
3. Set a repository variable `PUBLISH_TO_PYPI` to `true` (Settings, Secrets and
   variables, Actions, Variables).

After that, every `v*` tag uploads to PyPI as well. Without the variable the upload
is skipped. To publish by hand instead:

```bash
pip install build twine
python -m build
twine upload dist/*
```

A version can only be uploaded to PyPI once, so check `dist/` carefully first.

## What a yt-dlp update means

The Windows program carries the yt-dlp version from its build. When sites change and
downloads break, cut a new release. Nothing else needs to change: the dependency
is not pinned from above, so a rebuild picks up the newest yt-dlp.
`site_fixes.py` holds stopgaps for sites yt-dlp handles badly; delete each one
once a yt-dlp release fixes that site.
