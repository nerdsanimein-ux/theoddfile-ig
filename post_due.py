"""Runs on GitHub Actions: post every queued reel whose publish time has passed to Instagram, then delete its video.
queue.json: [{reel, publish_at (UTC 'YYYY-MM-DDTHH:MM:SSZ'), caption, video (repo path)}]; posted ones get "posted"."""
import json, os, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

GRAPH = "https://graph.facebook.com/v26.0"
TOK, UID = os.environ["IG_TOKEN"], os.environ["IG_USER_ID"]
RAW = f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/{os.environ.get('GITHUB_REF_NAME', 'main')}"


def call(method, path, **params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{GRAPH}/{path}" + ("" if method == "POST" else "?" + q),
                                 data=q.encode() if method == "POST" else None, method=method,
                                 headers={"Authorization": f"OAuth {TOK}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Instagram {e.code}: {e.read().decode()}")


queue = json.load(open("queue.json", encoding="utf-8"))
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
due = sorted((i for i in queue if not i.get("posted") and i["publish_at"] <= now), key=lambda i: i["publish_at"])
print(now, "due:", [i["reel"] for i in due] or "nothing")
for item in due:
    cont = call("POST", f"{UID}/media", media_type="REELS", video_url=f"{RAW}/{item['video']}",
                caption=item["caption"], share_to_feed="true")
    for _ in range(40):  # Instagram fetches and processes the video: up to ~10 min
        time.sleep(15)
        st = call("GET", cont["id"], fields="status_code,status")
        if st["status_code"] == "FINISHED": break
        if st["status_code"] in ("ERROR", "EXPIRED"): raise SystemExit(f"{item['reel']}: processing failed: {st}")
    else:
        raise SystemExit(f"{item['reel']}: still processing after 10 min")
    media = call("POST", f"{UID}/media_publish", creation_id=cont["id"])
    item["posted"] = call("GET", media["id"], fields="permalink").get("permalink", media["id"])
    item["posted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.remove(item["video"])  # ponytail: git history still keeps old videos; squash the repo if it nears GitHub's size limit
    json.dump(queue, open("queue.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)  # save after each post
    print(item["reel"], item["posted"], flush=True)
