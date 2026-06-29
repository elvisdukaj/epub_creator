# epub-creator

Build a single EPUB ebook from a list of web links. Each page is downloaded,
its main readable content is extracted (stripping navigation, sidebars, ads,
and in-page tables of contents), and the pages are bundled into one EPUB with a
generated table of contents.

Originally built to collect blog post series into offline-readable ebooks.

## Features

- Reads links from a text file (`--input`) and/or command-line arguments
- Downloads each page with rich progress feedback in the terminal
- Extracts the main article content using a heuristic content scorer
- Cleans out navigation, footers, comments, share buttons, and duplicated
  in-page TOC / "read this series in order" navigation
- Rewrites relative image URLs to absolute so they embed correctly, and turns
  unplayable video stills into plain links
- Makes heading/anchor ids unique across chapters so the TOC links resolve
  in-document instead of back to the original site
- Builds the EPUB with **Pandoc** (default) or **Calibre**'s `ebook-convert`

## Requirements

- Python >= 3.13
- Python packages: `requests`, `beautifulsoup4`, `rich`
- An external conversion tool:
  - [Pandoc](https://pandoc.org/) (default), **or**
  - [Calibre](https://calibre-ebook.com/) (provides `ebook-convert`)

## Installation

Using [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Or with pip:

```bash
pip install requests beautifulsoup4 rich
```

Make sure `pandoc` (or `ebook-convert`) is available on your `PATH`.

## Usage

From a file of links (one URL per line; blank lines and lines starting with `#`
are ignored):

```bash
python3 main.py \
    --input learn_rust.txt \
    --output learn_rust_by_example.epub \
    --title "Learn Rust by Example"
```

From URLs passed directly on the command line:

```bash
python3 main.py \
    --output mybook.epub \
    --title "Collected Articles" \
    https://example.com/page1 https://example.com/page2
```

With uv:

```bash
uv run main.py -i learn_bevy.txt -o learn_bevy_by_example.epub -t "Learn Bevy by Example"
```

### Options

| Flag | Description |
| --- | --- |
| `links` | URLs to include (positional, optional) |
| `--input`, `-i` | Text file with one URL per line |
| `--output`, `-o` | Output EPUB path (**required**) |
| `--title`, `-t` | Book title (**required**) |
| `--author`, `-a` | Book author |
| `--language`, `-l` | Language code, e.g. `en`, `de` (default: `en`) |
| `--engine` | Conversion backend: `pandoc` (default) or `calibre` |
| `--keep-temp` | Keep temporary files for debugging |

## How it works

1. Collect and de-duplicate the list of links.
2. For each URL, download the HTML and pick the highest-scoring content
   container (`<article>`, `<main>`, `.content`, etc.).
3. Strip site chrome and in-page navigation, normalize media URLs, and
   namespace anchor ids per chapter.
4. Write each cleaned chapter to a standalone XHTML file.
5. Run Pandoc / Calibre to merge the chapters into one EPUB with a table of
   contents.

## License

[MIT](LICENSE)
