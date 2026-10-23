const path = require("node:path");
const MEDIA_PATH =
  /^\/(?:stream\/\d+|manga\/\d+\/page\/\d+|external\/pawchive\/media\/[\w./-]+)$/;
const API_PATH =
  /^\/(?:auth|users|search-folder|folders|media|mobile|system|tags|ai|recommend|external|manga|x|dedup|stats|creators|bd2|auto-sync|thumbnails|stream|audio|discard|assistant)(?:\/|$)/;
function serverUrl(value) {
  if (typeof value !== "string" || !value.trim() || value.length > 2048)
    throw new Error("请输入服务器地址");
  let url;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error("地址只允许 HTTP/HTTPS，不要包含账号或参数");
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error("地址只允许 HTTP/HTTPS，不要包含账号或参数");
  return url.href.replace(/\/+$/, "");
}
function mediaRequest(base, value) {
  if (!base) throw new Error("请先连接 HE Manager 服务器");
  if (typeof value !== "string" || value.length > 20000)
    throw new Error("无效的媒体地址");
  const local = new URL(value, "he://app"),
    configured = new URL(base);
  const prefix = configured.pathname.replace(/\/$/, "");
  let pathname = local.pathname;
  if (local.origin === configured.origin && pathname.startsWith(prefix + "/"))
    pathname = pathname.slice(prefix.length);
  else if (local.protocol !== "he:" || local.host !== "app")
    throw new Error("只允许当前服务器的媒体");
  if (!MEDIA_PATH.test(pathname) || /(?:%|\.\.)/.test(pathname))
    throw new Error("不允许的媒体路径");
  const target = new URL(base + pathname),
    token = local.searchParams.get("token") || "";
  if (/[\r\n]/.test(token) || token.length > 16000)
    throw new Error("无效的登录凭证");
  for (const [key, value] of local.searchParams)
    if (key !== "token") target.searchParams.append(key, value);
  return {
    url: target.href,
    token,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  };
}
function staticPath(root, pathname) {
  const resolved = path.resolve(
    root,
    "." + decodeURIComponent(pathname === "/" ? "/index.html" : pathname),
  );
  const relative = path.relative(root, resolved);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative))
    throw new Error("不允许访问此文件");
  return resolved;
}
function shaderFiles(mode, root) {
  const names = {
    off: [],
    efficiency: [
      "Anime4K_Clamp_Highlights.glsl",
      "Anime4K_Restore_CNN_M.glsl",
      "Anime4K_Upscale_CNN_x2_M.glsl",
      "Anime4K_AutoDownscalePre_x2.glsl",
      "Anime4K_AutoDownscalePre_x4.glsl",
      "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
    quality: [
      "Anime4K_Clamp_Highlights.glsl",
      "Anime4K_Restore_CNN_VL.glsl",
      "Anime4K_Upscale_CNN_x2_VL.glsl",
      "Anime4K_AutoDownscalePre_x2.glsl",
      "Anime4K_AutoDownscalePre_x4.glsl",
      "Anime4K_Upscale_CNN_x2_M.glsl",
    ],
  }[mode];
  if (!names) throw new Error("未知的超分档位");
  return names.map((name) => path.join(root, name));
}
function allowPermission(permission, frameUrl) {
  if (permission !== "fullscreen") return false;
  try {
    const url = new URL(frameUrl);
    return (
      url.protocol === "he:" &&
      url.host === "app" &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}
function allowScreenshotDownload(url, mime, bytes) {
  return typeof url === 'string' && /^blob:he:\/\/app\/[a-z0-9-]+$/i.test(url)
    && mime === 'image/png' && Number.isFinite(bytes) && bytes >= 0 && bytes <= 64 * 1024 * 1024;
}
module.exports = {
  allowScreenshotDownload,
  serverUrl,
  mediaRequest,
  staticPath,
  shaderFiles,
  API_PATH,
  allowPermission,
};
