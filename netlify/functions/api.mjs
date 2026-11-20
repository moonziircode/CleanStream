/**
 * CleanStream Netlify Function API (Node.js)
 * High-performance serverless resolver & media streaming proxy.
 */

const USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const ID_REGEX = /(?:\/e\/|\/v\/|\/embed\/|\/d\/|\/)([a-zA-Z0-9_-]{6,32})(?:[/?#]|$)/;
const IFRAME_ID_REGEX = /var\s+iframeId\s*=\s*['"]([a-f0-9]+)['"]/;
const EMBED_TOKEN_REGEX = /var\s+embedToken\s*=\s*['"]([^'"]+)['"]/;
const SRC_REGEX = /(?:var\s+SRC|SRC)\s*=\s*['"]([^'"]+)['"]/;
const PLAYER_PATH_REGEX = /playerPath\s*=\s*['"]([^'"]+)['"]/;
const STREAM_PHP_REGEX = /https?:\/\/(?:streamrizz\.com|jwplyr\.com)\/stream\.php\?[^"'<>\s]+/;
const SOURCE_REGEX = /<source\s+[^>]*src=['"]([^'"]+)['"]/i;
const VIDEO_SRC_REGEX = /<video\s+[^>]*src=['"]([^'"]+)['"]/i;
const POSTER_REGEX = /poster=['"]([^'"]+)['"]/i;
const TITLE_REGEX = /<title>(.*?)<\/title>/i;

// In-memory cache for fast repeat requests
const resolveCache = new Map();
const CACHE_TTL_MS = 1800 * 1000;

function getCached(key) {
  const item = resolveCache.get(key);
  if (!item) return null;
  if (Date.now() > item.expiry) {
    resolveCache.delete(key);
    return null;
  }
  return item.value;
}

function setCache(key, value) {
  if (resolveCache.size >= 500) {
    const firstKey = resolveCache.keys().next().value;
    resolveCache.delete(firstKey);
  }
  resolveCache.set(key, { value, expiry: Date.now() + CACHE_TTL_MS });
}

function isSafeUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== "string") return false;
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
    const host = parsed.hostname.toLowerCase();
    if (host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0" || host === "::1") return false;
    if (host.includes("metadata.google.internal") || host.includes("169.254.169.254")) return false;
    // Check private IP patterns
    if (/^(?:10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|127\.|169\.254\.)/.test(host)) return false;
    return true;
  } catch {
    return false;
  }
}

function rewriteM3U8(content, baseUrl, proxyPrefix = "/api/stream?action=stream&url=") {
  const lines = content.split(/\r?\n/);
  const baseObj = new URL(baseUrl);
  const baseQuery = baseObj.search;

  function resolveUrl(u) {
    const abs = new URL(u, baseUrl).toString();
    if (baseQuery && !u.includes("?") && !abs.includes("?")) {
      return abs + baseQuery;
    }
    return abs;
  }

  const out = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      out.push(line);
    } else if (trimmed.startsWith("#")) {
      if (trimmed.includes('URI="')) {
        const replaced = trimmed.replace(/URI="([^"]+)"/g, (m, p1) => {
          const abs = resolveUrl(p1);
          return `URI="${proxyPrefix}${encodeURIComponent(abs)}"`;
        });
        out.push(replaced);
      } else {
        out.push(line);
      }
    } else {
      const abs = resolveUrl(trimmed);
      out.push(proxyPrefix + encodeURIComponent(abs));
    }
  }
  return out.join("\n");
}

async function resolveVidara(filecode) {
  const apiUrl = "https://vidwara.art/api/stream";
  const resp = await fetch(apiUrl, {
    method: "POST",
    headers: {
      "User-Agent": USER_AGENT,
      "Referer": `https://vidwara.art/e/${filecode}`,
      "Origin": "https://vidwara.art",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ filecode, device: "web" })
  });

  if (!resp.ok) {
    throw new Error(`Vidara upstream returned HTTP ${resp.status}`);
  }

  const data = await resp.json();
  const rawSource = data.streaming_url || data.url;
  if (!rawSource) {
    throw new Error(`Vidara stream URL tidak ditemukan untuk ID: ${filecode}`);
  }

  const title = data.title || `Vidara ${filecode}`;
  const poster = data.thumbnail || "";
  const isHls = rawSource.toLowerCase().includes(".m3u8");

  return {
    video_id: filecode,
    title,
    raw_mp4: rawSource,
    is_hls: isHls,
    original_name: rawSource.split("/").pop().split("?")[0],
    poster,
    embed_url: `https://vidara.to/v/${filecode}`
  };
}

async function resolveStreamrizz(inputUrlOrId) {
  const inputStr = inputUrlOrId.trim();
  const isVidara = inputStr.includes("vidara.to") || inputStr.includes("vidwara.art");

  let videoId = inputStr;
  const matchId = inputStr.match(ID_REGEX);
  if (matchId) {
    videoId = matchId[1];
  } else if (inputStr.includes("/")) {
    videoId = inputStr.replace(/\/+$/, "").split("/").pop().split("?")[0];
  }

  const cacheKey = `${isVidara ? "vidara" : "streamrizz"}:${videoId}`;
  const cached = getCached(cacheKey);
  if (cached) return cached;

  if (isVidara) {
    const result = await resolveVidara(videoId);
    setCache(cacheKey, result);
    return result;
  }

  const inputLower = inputStr.toLowerCase();
  let targetHost = "streamrizz.com";
  let preferredPath = "/e/";

  const hostMatch = inputStr.match(/(?:https?:\/\/)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/);
  if (hostMatch) {
    const rawHost = hostMatch[1].toLowerCase();
    if (rawHost.includes("filecoster.com")) targetHost = "filecoster.com";
    else if (rawHost.includes("jwplyr.com")) targetHost = "jwplyr.com";
    else if (rawHost.includes("vidoy")) targetHost = "filecoster.com";
    else if (rawHost.includes("streamrizz.com")) targetHost = "streamrizz.com";
  }

  const candidatePaths = [`/e/${videoId}`, `/d/${videoId}`];

  const candidateHosts = [targetHost];
  for (const alt of ["filecoster.com", "streamrizz.com", "jwplyr.com"]) {
    if (!candidateHosts.includes(alt)) candidateHosts.push(alt);
  }

  const baseHeaders = {
    "User-Agent": USER_AGENT,
    "Referer": `https://${targetHost}/`,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none"
  };

  let lastErr = null;

  for (const host of candidateHosts) {
    for (const p of candidatePaths) {
      try {
        const resp1 = await fetch(`https://${host}${p}`, {
          headers: {
            ...baseHeaders,
            "Referer": `https://${host}/`,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none"
          },
          signal: AbortSignal.timeout(6000)
        });

        if (resp1.status === 404) continue;
        const embedHtml = await resp1.text();
        if (embedHtml.includes("/404") || embedHtml.includes("404 Not Found") || embedHtml.includes("Page no longer exists")) {
          continue;
        }

        const cookie1 = resp1.headers.get("set-cookie") || "";

        // Step 1b: Extract iframe path
        let iframePath = "";
        const matchSrc = embedHtml.match(SRC_REGEX);
        if (matchSrc) {
          iframePath = matchSrc[1].replace(/\\u0026/g, "&").replace(/&amp;/g, "&");
          if (!iframePath.startsWith("/")) iframePath = "/" + iframePath;
        } else {
          const matchIframeId = embedHtml.match(IFRAME_ID_REGEX);
          const matchEmbedToken = embedHtml.match(EMBED_TOKEN_REGEX);
          if (!matchIframeId || !matchEmbedToken) {
            continue;
          }
          iframePath = `/ip129jk?id=${matchIframeId[1]}&t=${matchEmbedToken[1]}`;
        }

        // Step 2: Fetch Iframe Handshake
        const iframeHeaders = {
          ...baseHeaders,
          "Referer": `https://${host}${p}`,
          "Sec-Fetch-Dest": "iframe",
          "Sec-Fetch-Mode": "navigate",
          "Sec-Fetch-Site": "same-origin"
        };
        if (cookie1) iframeHeaders["Cookie"] = cookie1;

        const iframeResp = await fetch(`https://${host}${iframePath}`, {
          headers: iframeHeaders,
          signal: AbortSignal.timeout(6000)
        });
        const iframeHtml = await iframeResp.text();
        const cookie2 = iframeResp.headers.get("set-cookie") || cookie1;

        let playerPath = "";
        const matchPlayerPath = iframeHtml.match(PLAYER_PATH_REGEX) || iframeHtml.match(STREAM_PHP_REGEX);
        if (!matchPlayerPath) {
          continue;
        }
        playerPath = (matchPlayerPath[1] || matchPlayerPath[0]).replace(/\\u0026/g, "&").replace(/&amp;/g, "&");
        if (!playerPath.startsWith("http")) {
          playerPath = `https://${host}${playerPath.startsWith("/") ? "" : "/"}${playerPath}`;
        }

        // Step 3: Fetch Player Page for Media Source
        const playerHeaders = {
          ...baseHeaders,
          "Referer": `https://${host}${iframePath}`,
          "Sec-Fetch-Dest": "iframe",
          "Sec-Fetch-Mode": "navigate",
          "Sec-Fetch-Site": "same-origin"
        };
        if (cookie2) playerHeaders["Cookie"] = cookie2;

        const playerResp = await fetch(playerPath, {
          headers: playerHeaders,
          signal: AbortSignal.timeout(6000)
        });
        const playerHtml = await playerResp.text();

        const matchSource = playerHtml.match(SOURCE_REGEX) || playerHtml.match(VIDEO_SRC_REGEX);
        if (!matchSource) {
          continue;
        }

        const rawSource = matchSource[1].trim();
        const matchPoster = playerHtml.match(POSTER_REGEX);
        const matchTitle = playerHtml.match(TITLE_REGEX);

        const poster = matchPoster ? matchPoster[1] : `https://i.${host}/image/${videoId}.jpg`;
        const title = matchTitle ? matchTitle[1].replace(/&#(\d+);/g, (_, dec) => String.fromCharCode(dec)).trim() : `Video ${videoId}`;
        const isHls = rawSource.toLowerCase().includes(".m3u8");

        const result = {
          video_id: videoId,
          title,
          raw_mp4: rawSource,
          is_hls: isHls,
          original_name: rawSource.split("/").pop().split("?")[0],
          poster,
          embed_url: `https://${host}${p}`
        };

        setCache(cacheKey, result);
        return result;
      } catch (err) {
        lastErr = err;
      }
    }
  }

  throw lastErr || new Error(`Video tidak ditemukan atau telah dihapus oleh penyedia (404 Not Found) [ID: ${videoId}]`);
}

export const handler = async (event, context) => {
  const method = (event.httpMethod || "GET").toUpperCase();

  // Handle CORS Preflight
  if (method === "OPTIONS") {
    return {
      statusCode: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, Authorization, Accept-Encoding, User-Agent, Referer",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
        "Access-Control-Max-Age": "86400"
      },
      body: ""
    };
  }

  const path = event.path || "/";
  const params = event.queryStringParameters || {};
  const action = (params.action || "").toLowerCase();
  const targetUrl = (params.url || "").trim();
  const targetUrlLower = targetUrl.toLowerCase();

  const isStreamRoute = (
    action === "stream" ||
    path.includes("/stream") ||
    path.endsWith("stream") ||
    [".mp4", ".m3u8", ".ts", ".key", "overfetch"].some(ext => targetUrlLower.includes(ext))
  );

  // ---------------------------------------------------------------------------
  // Route: /api/stream (Media Proxy & Playlist Rewriter)
  // ---------------------------------------------------------------------------
  if (isStreamRoute && targetUrl) {
    if (!isSafeUrl(targetUrl)) {
      return {
        statusCode: 403,
        headers: { "Content-Type": "text/plain", "Access-Control-Allow-Origin": "*" },
        body: "Forbidden URL: Akses target tidak diizinkan"
      };
    }

    const parsedTarget = new URL(targetUrl);
    const targetNetloc = parsedTarget.hostname.toLowerCase();
    let proxyReferer = `${parsedTarget.protocol}//${parsedTarget.hostname}/`;
    if (targetNetloc.includes("streamrizz") || targetNetloc.includes("jwplyr") || targetNetloc.includes("overfetch")) {
      proxyReferer = "https://streamrizz.com/";
    } else if (targetNetloc.includes("filecoster") || targetNetloc.includes("vidoy")) {
      proxyReferer = "https://filecoster.com/";
    } else if (targetNetloc.includes("vidwara") || targetNetloc.includes("97bf1.com")) {
      proxyReferer = "https://vidwara.art/";
    }

    const reqHeaders = {
      "User-Agent": USER_AGENT,
      "Referer": proxyReferer
    };

    const isM3u8 = targetUrlLower.includes(".m3u8");

    // Range clamping to prevent serverless 6MB payload limit & 504 timeouts on large MP4 files
    const MAX_CHUNK = 2 * 1024 * 1024; // 2 MB per chunk
    const clientRange = event.headers?.range || event.headers?.Range || "";
    let upstreamRange = null;

    if (!isM3u8 && method !== "HEAD") {
      if (clientRange) {
        const match = clientRange.match(/bytes=(\d+)-(\d+)?/i);
        if (match) {
          const start = parseInt(match[1], 10);
          let end = match[2] ? parseInt(match[2], 10) : null;
          if (end === null || (end - start + 1) > MAX_CHUNK) {
            end = start + MAX_CHUNK - 1;
          }
          upstreamRange = `bytes=${start}-${end}`;
        } else {
          upstreamRange = clientRange;
        }
      } else if (!targetUrlLower.includes(".ts")) {
        // If client didn't specify Range for MP4, request first chunk to prevent downloading entire 100MB+ file
        upstreamRange = `bytes=0-${MAX_CHUNK - 1}`;
      }
    }

    if (upstreamRange) {
      reqHeaders["Range"] = upstreamRange;
    } else if (clientRange) {
      reqHeaders["Range"] = clientRange;
    }

    try {
      const upstreamResp = await fetch(targetUrl, {
        method: method === "HEAD" ? "HEAD" : "GET",
        headers: reqHeaders,
        signal: AbortSignal.timeout(10000)
      });

      const statusCode = upstreamResp.status;
      const contentType = upstreamResp.headers.get("content-type") || "";
      const isM3u8Resp = isM3u8 || contentType.toLowerCase().includes("mpegurl");

      // Case A: M3U8 Playlist (Rewrite URLs)
      if (isM3u8Resp && method !== "HEAD") {
        const m3u8Content = await upstreamResp.text();
        const rewritten = rewriteM3U8(m3u8Content, targetUrl, "/api/stream?action=stream&url=");
        return {
          statusCode: 200,
          headers: {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Content-Length": String(Buffer.byteLength(rewritten, "utf8")),
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
            "Cache-Control": "public, max-age=60"
          },
          body: rewritten
        };
      }

      // Case B: HEAD Request
      if (method === "HEAD") {
        const outHeaders = {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
          "Accept-Ranges": "bytes"
        };
        for (const [k, v] of upstreamResp.headers.entries()) {
          if (["content-type", "content-length", "content-range", "etag", "last-modified"].includes(k.toLowerCase())) {
            outHeaders[k] = v;
          }
        }
        return {
          statusCode: statusCode === 200 ? 200 : statusCode,
          headers: outHeaders,
          body: ""
        };
      }

      // Case C: Binary Media / TS Segment / MP4
      let mimetype = "video/mp4";
      if (targetUrlLower.includes(".ts")) {
        mimetype = "video/mp2t";
      } else if (contentType) {
        mimetype = contentType;
      }

      const arrayBuffer = await upstreamResp.arrayBuffer();
      const buffer = Buffer.from(arrayBuffer);

      const outHeaders = {
        "Content-Type": mimetype,
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
        "Accept-Ranges": "bytes",
        "Content-Length": String(buffer.length),
        "Cache-Control": targetUrlLower.includes(".ts") ? "public, max-age=86400, immutable" : "public, max-age=3600"
      };

      const upstreamContentRange = upstreamResp.headers.get("content-range");
      if (upstreamContentRange) {
        outHeaders["Content-Range"] = upstreamContentRange;
      }
      const upstreamEtag = upstreamResp.headers.get("etag");
      if (upstreamEtag) outHeaders["ETag"] = upstreamEtag;

      return {
        statusCode: statusCode === 206 || upstreamContentRange ? 206 : statusCode,
        headers: outHeaders,
        body: buffer.toString("base64"),
        isBase64Encoded: true
      };
    } catch (err) {
      return {
        statusCode: 502,
        headers: { "Content-Type": "text/plain", "Access-Control-Allow-Origin": "*" },
        body: `Streaming error: ${err.message}`
      };
    }
  }

  // ---------------------------------------------------------------------------
  // Route: /api/resolve (Video Resolver)
  // ---------------------------------------------------------------------------
  if (targetUrl) {
    try {
      const info = await resolveStreamrizz(targetUrl);
      return {
        statusCode: 200,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
          "Cache-Control": "public, max-age=300"
        },
        body: JSON.stringify({ status: "ok", ...info })
      };
    } catch (err) {
      const errMsg = err.message || String(err);
      const is404 = errMsg.includes("404") || errMsg.toLowerCase().includes("tidak ditemukan");
      return {
        statusCode: is404 ? 404 : 500,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*"
        },
        body: JSON.stringify({ status: "error", message: errMsg })
      };
    }
  }

  // ---------------------------------------------------------------------------
  // Default Service Info Route
  // ---------------------------------------------------------------------------
  return {
    statusCode: 200,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*"
    },
    body: JSON.stringify({ status: "ok", service: "CleanStream Netlify API" })
  };
};
