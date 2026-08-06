// AIAuto API client — Node.js example (Node 18+, built-in fetch).
// Works the same in React/Next.js API routes — never expose the key in
// browser code; call this from YOUR backend.

const BASE = "https://your-server/api/public/v1";
const KEY = "ak_your_api_key_here";
const HEADERS = { "X-API-Key": KEY, "Content-Type": "application/json" };

async function submitText(prompt) {
  const res = await fetch(`${BASE}/text`, {
    method: "POST", headers: HEADERS, body: JSON.stringify({ prompt }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

async function submitImage(prompt) {
  const res = await fetch(`${BASE}/images`, {
    method: "POST", headers: HEADERS, body: JSON.stringify({ prompt }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

async function waitFor(jobId, timeoutMs = 600000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await (await fetch(`${BASE}/jobs/${jobId}`,
      { headers: { "X-API-Key": KEY } })).json();
    if (["completed", "failed", "cancelled"].includes(job.status)) return job;
    await new Promise(r => setTimeout(r, 3000));
  }
  throw new Error(`timeout waiting for job ${jobId}`);
}

async function downloadFile(fileId, dest) {
  const fs = await import("node:fs/promises");
  const res = await fetch(`${BASE}/files/${fileId}`, { headers: { "X-API-Key": KEY } });
  await fs.writeFile(dest, Buffer.from(await res.arrayBuffer()));
}

// Express webhook receiver with signature verification
// app.post("/aiauto-hook", express.raw({type: "*/*"}), (req, res) => {
//   const crypto = require("node:crypto");
//   const ts = req.header("X-AIAuto-Timestamp");
//   const sig = req.header("X-AIAuto-Signature");
//   const expected = crypto.createHmac("sha256", WEBHOOK_SECRET)
//     .update(`${ts}.`).update(req.body).digest("hex");
//   if (Math.abs(Date.now()/1000 - Number(ts)) > 300 ||
//       !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected)))
//     return res.status(401).end();
//   const { event, data } = JSON.parse(req.body);
//   console.log(event, data.job_id);
//   res.json({ ok: true });
// });

(async () => {
  let job = await submitText("Write a friendly reminder email about the team meeting");
  console.log("submitted", job.id);
  job = await waitFor(job.id);
  console.log(job.status, job.response ?? job.error);
})();
