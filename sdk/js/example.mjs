// node example.mjs photo.jpg   (Node ≥ 18; set SEGIMAGE_URL to use your own server)
import { readFile, writeFile } from "node:fs/promises";
import { SegImage, SegImageError } from "./segimage.js";

const client = new SegImage(process.env.SEGIMAGE_URL || "https://jev.fishmaple.cn/segImage");
const h = await client.health();
console.log("server", h.version, "limits", h.limits);

const img = new Blob([await readFile(process.argv[2] || "photo.jpg")], { type: "image/jpeg" });
const res = await client.segment(img, { method: "rembg", smooth: 3 });
await writeFile("sticker.png", Buffer.from(await res.image.arrayBuffer()));
console.log(res.engine, `${res.width}x${res.height}`, `${res.elapsed_ms} ms -> sticker.png`);

try { await client.segment(new Blob(["not an image"])); }
catch (e) { if (e instanceof SegImageError) console.log("expected error:", e.code); else throw e; }
