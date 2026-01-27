# Kagi Small Web

Kagi Small Web is an initiative by [Kagi](https://kagi.com).

Kagi's mission is to humanize the web and this project is built to help surface recent results from the small web - people and stories that typically zip by in legacy search engines. Read more about it in the announcement [blog post](https://blog.kagi.com/small-web).

Few things to note:

- [Kagi search engine](https://kagi.com) surfaces posts from the small web for relevant queries in its search results. 

- Try the [Kagi Small Web](https://kagi.com/smallweb) website.

- You can also use the [RSS feed](https://kagi.com/api/v1/smallweb/feed) or access these results as a part of a broader [Kagi News Enrichment API](https://help.kagi.com/kagi/api/enrich.html). 

- There is an [OPML file](https://kagi.com/smallweb/opml) of the sites which make up the above RSS feed

## Criteria for posts to show on the website

If the blog is included in small web feed list (which means it has content in English, it is informational/educational by nature and it is not trying to sell anything) we check for these two things to show it on the site:

- Blog has recent posts (<7 days old)
- The website can appear in an iframe
  
## ⚠️ Guidelines for adding a site or channel to the list ⚠️

Add a new personal blog RSS feed to the list. Rules:

- **If submitting your own website, you must add at least 2 other sites that are not yours (and are not in list yet) in the same commit.**
- Locate and submit the RSS feed of the website. Place in the file so that it remains sorted.
- Content must be in English (currently, other languages are not accepted).
- No illegal or NSFW content.
- No auto generated, LLM generated or spam content.
- Only personal blogs may be submitted. 
- The blog must have a recent post, no older than 12 months, to meet the recency criteria for inclusion.
- The site must not contain any forms of advertisements or undisclosed affiliate links
- Site should not have newsletter signup popups (substack sites are not accepted too)
- A YT channel must not post more than twice a week.
- A YT channel must have fewer than 400,000 subscribers.

For comics:
- Must be independently created art (no AI generated content)
- RSS feed must show the full comic in the feed
- No commercial syndicated comics

[Add website RSS
feed](https://github.com/kagisearch/smallweb/edit/main/smallweb.txt)

Hint: To extract the RSS link from a YouTube channel, you can use [this tool](https://youtube-rss-nu.vercel.app/).

[Add YouTube channel RSS
feed](https://github.com/kagisearch/smallweb/edit/main/smallyt.txt)

[Add Comic RSS
feed](https://github.com/kagisearch/smallweb/edit/main/smallcomic.txt)

## Remove a site or a channel

Remove a website if :

- It does not adhere to the above guidelines
- In the removal request, state which guideline does it break

Clicking "Remove website" will edit small web list in new tab, where you can locate and remove the website feed in question. Make sure to add in comments the reason for removal.

[Remove website](https://github.com/kagisearch/smallweb/edit/main/smallweb.txt)

[Remove channel](https://github.com/kagisearch/smallweb/edit/main/smallt.txt)

## The Small Web seal: badge of authentic creation
Small Web initiative members can display badges on their websites to identify themselves as part of a community committed to authentic, human-centered content.

![Small Web Seal](https://kagifeedback.org/assets/files/2025-11-27/1764250797-487602-80x15-1.png)

![Small Web Seal](https://kagifeedback.org/assets/files/2025-11-27/1764250950-635837-80x15-2.png)

![Small Web Seal](https://kagifeedback.org/assets/files/2025-11-27/1764250973-708369-88x31-2.gif)

![Small Web Seal](https://kagifeedback.org/assets/files/2025-11-27/1764250993-634450-88x31-2.png)

![Small Web Seal](https://kagifeedback.org/assets/files/2025-11-27/1764251011-383809-88x31-3.jpg)

![Small Web Seal](https://kagifeedback.org/assets/files/2025-11-27/1764251027-352511-88x31-4.gif)

![Small Web Seal](https://kagifeedback.org/assets/files/2025-11-27/1764251045-794944-88x31-4.png)

## Small web is beautiful

What is Small Web exactly? Recommend reading:

- https://neustadt.fr/essays/the-small-web/
- https://benhoyt.com/writings/the-small-web-is-beautiful/
- https://smallweb.page/why
- https://ar.al/2020/08/07/what-is-the-small-web/
- https://news.ycombinator.com/item?id=29768197



## Info

[smallweb.txt](https://github.com/kagisearch/smallweb/blob/main/smallweb.txt) - Contains the feeds of indexed blogs

[smallyt.txt](https://github.com/kagisearch/smallweb/blob/main/smallyt.txt) - Contains the feeds of indexed YouTube channels

[smallcomic.txt](https://github.com/kagisearch/smallweb/blob/main/smallcomic.txt) - Contains the feeds of indexed independent comics

[yt_rejected.txt](https://github.com/kagisearch/smallweb/blob/main/yt_rejected.txt) - Contains the list of YouTube channels that were reviewed (in an automated way) and rejected 

app/ - App powering the Kagi Small Web website



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
- https://uses.tech
- https://nownownow.com
- https://personalsit.es




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



### Useful commands

Show duplicate domains:
```
awk -F/ '{print $3}' smallweb.txt | sort | uniq -d | while read domain; do echo "$domain"; grep "$domain" smallweb.txt; echo ""; done
```
