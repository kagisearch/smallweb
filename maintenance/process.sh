#!/bin/bash

SMALLWEB='../smallweb.txt'
CRAWL_RESULTS='crawl-result.csv'
URLS_404='404.csv'
URLS_UNCHANGED='unchanged.csv'
URLS_CHANGED='changed.csv'
TMP='tmp.csv'



echo "Split results into different categories (files)..."

# Copy header to new files
head --lines=1 "$CRAWL_RESULTS" > "$URLS_404"
head --lines=1 "$CRAWL_RESULTS" > "$URLS_UNCHANGED"
head --lines=1 "$CRAWL_RESULTS" > "$URLS_CHANGED"

while IFS="	" read -r url host exitcode url_effective response_code; do
  if [[ "$exitcode" == "0" ]] && [[ "$response_code" == "404" ]]; then
    # 404 - These pages exist but something seems to have changed, maybe the
    # feed is gone or the location has changed.
    #
    #  This can't be resolved automatically -> write to separate file so they
    # can be reviewed manually.
    echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$URLS_404"
  elif [[ "$exitcode" == "0" ]] && [[ "$response_code" == "200" ]]; then

    if [[ "$url" == "$url_effective" ]]; then
      # 200 and url did not change
      echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$URLS_UNCHANGED"
    else
      # Treat custom domains in front of generic feed providers as "unchanged"
      if echo "$url_effective" | grep -q "buttondown.com\|feedblitz.com\|feedburner.com\|feedpress.me\|paragraph.com"; then
        echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$URLS_UNCHANGED"
      else
        echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$URLS_CHANGED"
      fi
    fi
  else
    echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$URLS_CHANGED"
  fi

# '--lines=+2' to skip the csv header
done <<< "$(tail --lines=+2 "$CRAWL_RESULTS")"




# shellcheck disable=SC2162
read -p "Press enter to continue"
echo "Update simple redirects..."

# Copy header to new files
head --lines=1 "$URLS_CHANGED" > "$TMP"

while IFS="	" read -r url host exitcode url_effective response_code; do
  if [[ "$exitcode" != "0" ]] || [[ "$response_code" != "200" ]]; then
    echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$TMP"
    continue
  fi

  # Trim scheme
  # shellcheck disable=SC2001
  OLD_URL=$(sed 's>^https\?://>>g' <<<"$url")
  # shellcheck disable=SC2001
  NEW_URL=$(sed 's>^https\?://>>g' <<<"$url_effective")
  # Trim trailing slashes
  # shellcheck disable=SC2001
  OLD_URL=$(sed 's>/\+$>>g' <<<"$OLD_URL")
  # shellcheck disable=SC2001
  NEW_URL=$(sed 's>/\+$>>g' <<<"$NEW_URL")

  # If the old and new URL only differ in these minor details, replace the
  # original url with the new one.
  if [[ "$OLD_URL" == "$NEW_URL" ]]; then
    sed -i "s>^${url}\$>${url_effective}>g" "$SMALLWEB"
  else
    echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$TMP"
  fi
done <<< "$(tail --lines=+2 "$URLS_CHANGED")"

mv "$TMP" "$URLS_CHANGED"



# shellcheck disable=SC2162
read -p "Press enter to continue"
echo "Verify and remove unresolvable domains..."

# Wether curl can resolve a domain depends on the DNS settings of the machine
# this script is run on. We know from experience that some domains might be a
# bit flaky, they might be present on one DNS servers and missing on another
# one.
#
# We don't want to be too aggressive, so we check multiple popular DNS servers.
# Only if none of them can resolve the domain, we remove it.
#
# In theory we could avoid these extra lookups and straight up delete
# unresolvable domains if we told curl to use these popular DNS server while
# crawling. e.g.:
#
#   curl --dns-servers 8.8.8.8,1.1.1.1,9.9.9.9 [...]
#
# But this requires a libcurl build with c-ares support, which doesn't seem to
# be popular/the default on many platforms. So let's stick with this solution
# that might be worse but should work on most setups.

# Copy header to new files
head --lines=1 "$URLS_CHANGED" > "$TMP"

# A few popular DNS servers
# Google, Cloudflare, Quad9
DNS_SERVERS=("8.8.8.8" "1.1.1.1" "9.9.9.9")

while IFS="	" read -r url host exitcode url_effective response_code; do
  if [[ "$exitcode" != "6" ]]; then
    echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$TMP"
    continue
  fi

  found=false
  for SERVER in "${DNS_SERVERS[@]}"; do
    query_result=$(dig "@$SERVER" "$host" +short)

    if [ -n "$query_result" ]; then
      found=true
      break
    fi
  done

  if [[ $found == true ]] ; then
    echo -e "${url}\t${host}\t${exitcode}\t${url_effective}\t${response_code}" >> "$TMP"
  else
    sed -i "\	^${url}\$	d" "$SMALLWEB"
  fi
done <<< "$(tail --lines=+2 "$URLS_CHANGED")"

mv "$TMP" "$URLS_CHANGED"
