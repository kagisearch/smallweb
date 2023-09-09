# Kagi Small Web

Kagi's mission is to humanize the web and this project is built to help surface recent (7 day old or newer) results from the small web - people and stories that typically zip by in legacy search engines. Read more about it in the announcement [blog post](https://blog.kagi.com/small-web).

Few things to note:

- [Kagi search engine](https://kagi.com) now surfaces posts from the small web for relevant queries in its search results. 

- Try the [Kagi Small Web](https://kagi.com/smallweb) website to read and appreciate the posts directly.

- You can also use the [RSS feed](https://kagi.com/api/v1/smallweb/feed) or access these results as a part of a broader [Kagi News Enrichment API](https://help.kagi.com/kagi/api/enrich.html). 

## Criteria for posts to show on the KSW website

If the blog is included in small web feed list (which means it has content in English, it is informational/educational by nature and it is not trying to sell anything) we check for these two things to show it on the site:

- Blog has recent posts (<7 days old)
- The website can appear in an iframe
  
## Small web is beautiful

What is Small Web exactly? Recommend reading:

- https://neustadt.fr/essays/the-small-web/
- https://benhoyt.com/writings/the-small-web-is-beautiful/
- https://smallweb.page/why
- https://ar.al/2020/08/07/what-is-the-small-web/
- https://news.ycombinator.com/item?id=29768197



## Info

[smallweb.txt](https://github.com/kagisearch/smallweb/edit/main/smallweb.txt) - Contains the feeds of indexed blogs

[smallyt.txt](https://github.com/kagisearch/smallweb/edit/main/smallyt.txt) - Contains the feeds of indexed YouTube channels

[yt_rejected.txt](https://github.com/kagisearch/smallweb/edit/main/yt_rejected.txt) - Contains the list of YouTube channels that were reviewed (in an automated way) and rejected 

app/ - App powering the Kagi Small Web website


## Add a site or channel to the list

Add a new personal blog RSS feed to the list. Rules:

- Do not submit your own website unless you submit 2 other sites that are not yours (and are not in list).
- Locate and submit the RSS feed of the website.
- Content must be in English (currently, other languages are not accepted).
- Only personal blogs may be submitted.
- The blog must have a recent post, no older than 6 months, to meet the recency criteria for inclusion.
- The site must not contain any forms of monetization, such as advertisements, newsletter signup popups, etc.

[Add website RSS
feed](https://github.com/kagisearch/smallweb/edit/main/smallweb.txt)


Add a new YouTube channel RSS feed to the list. Rules:

- Do not submit your own YouTube channel unless you submit 2 other channels that are not yours (and are not in list).
- Locate and submit the RSS feed of the YouTube channel.
- Content must be in English (currently, other languages are not accepted).
- Preference is given to channels focusing on hobbies or passions.
- The channel must not post more than twice a week.
- The channel must have fewer than 400,000 subscribers.

Hint: To extract the RSS link from a YouTube channel, you can use [this tool](https://youtube-rss-nu.vercel.app/).

[Add YouTube channel RSS
feed](https://github.com/kagisearch/smallweb/edit/main/smallyt.txt)

## Remove a site or a channel

Remove a website if :

- Content is not in English.
- Website has poor quality content.
- Website contains intrusive monetization such as ads or newsletter popups.
- Website purpose is monetization rather than education.


Clicking "Remove website" will edit small web list in new tab, where you can locate and remove the website feed in question. Make sure to add in comments the rason for removal.

[Remove website](https://github.com/kagisearch/smallweb/edit/main/smallweb.txt)


Remove a YouTube channel if :

- Content is not in English.
- Channel has poor quality content.
- Channel's purpose is monetization rather than education.

Clicking "Remove" will edit small youtube list in new tab, where you can locate and remove the YouTube channel feed in question. Make sure to add in comments the reason for removal.

[Remove channel](https://github.com/kagisearch/smallweb/edit/main/smallt.txt)

## Sources
### Small web 

The original list of small web blogs has been assembled from various
sources including:

- https://github.com/outcoldman/hackernews-personal-blogs
- https://news.ycombinator.com/item?id=22273224
- https://news.ycombinator.com/item?id=15154903
- https://news.ycombinator.com/item?id=30245247
- https://news.ycombinator.com/item?id=29758396
- https://news.ycombinator.com/item?id=27302195
- https://github.com/rushter/data-science-blogs
- https://github.com/kilimchoi/engineering-blogs#-individuals
- https://github.com/ysfelouardi/awesome-personal-blogs?search=1
- https://ooh.directory/blogs/personal/
- https://indieblog.page/all
- https://biglist.terraaeon.com
- https://tech-blogs.dev
- https://hn-blogs.kronis.dev/all-blogs.html
- https://dm.hn


### YouTube channels

The seed list for YouTube channels has been assembled from these HN discussions.

- https://news.ycombinator.com/item?id=32220192
- https://news.ycombinator.com/item?id=25647657
- https://news.ycombinator.com/item?id=32378309
- https://news.ycombinator.com/item?id=20385679
- https://news.ycombinator.com/item?id=24374979
- https://news.ycombinator.com/item?id=24589474
- https://news.ycombinator.com/item?id=24671019
- https://news.ycombinator.com/item?id=35120777
- https://news.ycombinator.com/item?id=12702651
- https://news.ycombinator.com/item?id=17202615
- https://news.ycombinator.com/item?id=29666539



