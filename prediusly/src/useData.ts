import { useState, useEffect } from 'react';

export function useData() {
  const [predictions, setPredictions] = useState<any>(null);
  const [pipelineSteps, setPipelineSteps] = useState<any>(null);
  const [modelComparison, setModelComparison] = useState<any>(null);
  const [shapGlobal, setShapGlobal] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadAll() {
      try {
        const [predRes, pipeRes, modelRes, shapRes] = await Promise.all([
          fetch('/api/predictions'),
          fetch('/api/pipeline-steps'),
          fetch('/api/model-comparison'),
          fetch('/api/shap-global'),
        ]);

        const pred = await predRes.json();
        const pipe = await pipeRes.json();
        const mod = await modelRes.json();
        const shap = await shapRes.json();

        setPredictions(pred);
        setPipelineSteps(pipe);
        setModelComparison(mod);
        setShapGlobal(shap);
      } catch (err) {
        console.error("Error loading data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadAll();
  }, []);

  return { predictions, pipelineSteps, modelComparison, shapGlobal, loading };
}
