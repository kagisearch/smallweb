#!/bin/bash

SMALLWEB=../smallweb.txt

# Verify smallweb doesn't contain tabs by itself.
# This should always be the case, but let's just be safe. This way we can
# securely use tab as a separator
if grep "$SMALLWEB" -q -e "	"; then
  echo "$SMALLWEB contains tabs. Aborting..."
  exit 1
fi

OUTPUT='crawl-result.csv'
CURL_COLUMNS='%{url}\t%{url.host}\t%{exitcode}\t%{url_effective}\t%{response_code}'
CSV_HEADER='url\texitcode\turl_effective\tresponse_code'

# Avoid writing header when amending an existing result file.
# (useful if you fiddle around)
if [ ! -f "$OUTPUT" ]; then
  echo -e "$CSV_HEADER" >> "$OUTPUT"
fi

while read -r URL; do
  curl --max-time 30 -Ls --head -o /dev/null --write-out "${CURL_COLUMNS}\n" "$URL" >> "$OUTPUT"
done < $SMALLWEB
