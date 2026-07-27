/*
 * Reaction networking for the post deck. Similarity lookup is lazy and
 * cancellable; a reaction is successful only after the API acknowledges it.
 */
window.createSmallWebLikeClient = ({
  likeUrl,
  targetUrl,
  timeoutMs,
  currentUrl,
  onTarget,
}) => {
  let target = null;
  let targetFor = '';
  let targetPromise = null;
  let targetController = null;

  function reset() {
    if (targetController) targetController.abort();
    target = null;
    targetFor = '';
    targetPromise = null;
    targetController = null;
  }

  async function prepare() {
    if (!targetUrl) return null;
    const requestedFor = currentUrl();
    if (targetFor === requestedFor) {
      if (target) return target;
      if (targetPromise) return targetPromise;
    }

    reset();
    targetFor = requestedFor;
    const sep = targetUrl.includes('?') ? '&' : '?';
    const url = `${targetUrl}${sep}url=${encodeURIComponent(requestedFor)}`;
    const controller = new AbortController();
    targetController = controller;
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const request = (async () => {
      try {
        const res = await fetch(url, {
          signal: controller.signal,
          headers: {Accept: 'application/json'},
        });
        if (!res.ok) return null;
        const data = await res.json();
        if (currentUrl() !== requestedFor || !data?.post) return null;
        target = data.post;
        onTarget(target);
        return target;
      } catch {
        return null;
      } finally {
        clearTimeout(timer);
      }
    })();

    targetPromise = request;
    const result = await request;
    if (targetPromise === request) {
      targetPromise = null;
      targetController = null;
    }
    return result;
  }

  async function save(form) {
    if (!likeUrl) return false;
    const url = form.querySelector('input[name="url"]')?.value;
    const emoji = form.querySelector('input[name="emoji"]')?.value;
    if (!url) return false;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(likeUrl, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url, emoji}),
        signal: controller.signal,
        keepalive: true,
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  return {prepare, reset, save};
};
