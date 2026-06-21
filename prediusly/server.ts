const PORT = 3001;

const headers = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);

    if (req.method === "OPTIONS") {
      return new Response("OK", { headers });
    }

    try {
      if (url.pathname === "/api/predictions") {
        const file = Bun.file("data/predictions.geojson");
        return new Response(file, { headers: { ...headers, "Content-Type": "application/json" } });
      }

      if (url.pathname === "/api/pipeline-steps") {
        const file = Bun.file("data/pipeline_steps.json");
        return new Response(file, { headers: { ...headers, "Content-Type": "application/json" } });
      }

      if (url.pathname === "/api/model-comparison") {
        const file = Bun.file("data/model_comparison.json");
        return new Response(file, { headers: { ...headers, "Content-Type": "application/json" } });
      }

      if (url.pathname === "/api/shap-global") {
        const file = Bun.file("data/shap_global.json");
        return new Response(file, { headers: { ...headers, "Content-Type": "application/json" } });
      }

      return new Response("Not Found", { status: 404, headers });
    } catch (e) {
      return new Response("Error loading data", { status: 500, headers });
    }
  },
});

console.log(`Backend server running at http://localhost:${PORT}`);
