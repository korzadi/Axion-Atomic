import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate } from "k6/metrics";

const unexpected = new Counter("unexpected_responses");
const overload = new Counter("controlled_overload_responses");
const healthy = new Rate("health_available");

export const options = {
  stages: [
    { duration: "1m", target: 10 },
    { duration: "2m", target: 10 },
    { duration: "1m", target: 100 },
    { duration: "2m", target: 100 },
    { duration: "1m", target: 1000 },
    { duration: "2m", target: 1000 },
    { duration: "1m", target: 0 },
  ],
  thresholds: {
    unexpected_responses: ["count==0"],
    health_available: ["rate>0.99"],
  },
};

const base = __ENV.BASE_URL;
const session = __ENV.AXION_SESSION;
const csrf = __ENV.AXION_CSRF;
const project = __ENV.AXION_PROJECT_ID;

export default function () {
  if (!base || !session || !csrf || !project) {
    throw new Error("Define BASE_URL, AXION_SESSION, AXION_CSRF y AXION_PROJECT_ID");
  }

  const response = http.post(
    `${base}/workspace/chat/completions`,
    JSON.stringify({
      model: "atomic-code:16k-8k",
      project_id: project,
      messages: [{ role: "user", content: "Responde brevemente: prueba de capacidad." }],
      stream: false,
      max_tokens: 32,
    }),
    {
      headers: {
        "Content-Type": "application/json",
        "Cookie": `axion_session=${session}; axion_csrf=${csrf}`,
        "X-CSRF-Token": csrf,
      },
      timeout: "90s",
      tags: { endpoint: "workspace-chat" },
    },
  );

  const accepted = check(response, {
    "chat accepted or safely backpressured": (r) => [200, 429, 503].includes(r.status),
  });
  if (!accepted) unexpected.add(1);
  if (response.status === 429 || response.status === 503) overload.add(1);

  if (__VU % 25 === 0) {
    const health = http.get(`${base}/health`, { timeout: "5s" });
    healthy.add(health.status === 200);
    if (health.status !== 200) unexpected.add(1);
  }
  sleep(1);
}
