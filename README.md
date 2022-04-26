Sefaria-Export
============

Structured Jewish texts and metadata with free public licenses, exported from Sefaria's database.

This repo contains texts, bibliographical information and lists of intertextual connections created by [Sefaria](http://www.sefaria.org).

A MongoDB dump of Sefaria's database is also available for download [here](https://storage.googleapis.com/sefaria-mongo-backup/dump.tar.gz) or a smaller version (without text edit history) [here](https://storage.googleapis.com/sefaria-mongo-backup/dump_small.tar.gz). Download this file, extract it and use [`mongorestore`](http://docs.mongodb.org/v2.2/reference/mongorestore/) to load into your local DB.

From the parent of the unzipped `dump` folder, run:

    mongorestore --drop

This will create (or overwrite) a mongo database called `sefaria`.

More details available [here](https://github.com/Sefaria/Sefaria-Project#8-put-some-texts-in-your-database).

For Sefaria source code see [Sefaria-Project](https://github.com/Sefaria/Sefaria-Project).

### Contents

* `/json/` - simple json output of texts
* `/txt/` - simple plain text output of texts
* `/xml/` - simple xml output of texts (coming as soon as requested)
* `/links/` - CSV output of all known interconnections in texts
* `/schemas/` - JSON files corresponding to schema information about each text
* `/misc` - other miscellaneous data outputs

Text output folders are organized by category and contain seperate directories for each language. Each file is named according the version of the particular text. 

Each terminal directory also includes a file called `merged` (e.g., `merged.json` or `merged.txt`). This file uses the same logic used on the Sefaria web site to include the maximal content available. For example, we have cases in the Mishnah where no single English version is complete by itself, but the merged version will include a complete text that picks and merges from multiple sources as needed.

When we do have complete versions of texts, we will still include a merged file. In that case, the merged file will be a copy of the default complete version. This simplifies many applications - you are always guaranteed that by looking at the merged version you'll see a maximal amount of text available, with preference for the text versions we've set. 

Code for generating these files can be found in our [Sefaria-Project](https://github.com/Sefaria/Sefaria-Project) repo under [sefaria/export.py](https://github.com/Sefaria/Sefaria-Project/blob/master/sefaria/export.py).
