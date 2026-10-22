UPDATE soclite.triage_results
SET summary = replace(summary, 'autom??tico', 'automático')
WHERE summary LIKE '%??%';

UPDATE soclite.triage_results
SET reasoning = '["Análisis de reputación del indicador","Correlación con eventos previos del activo","Evaluación de criticidad del activo destino"]'::jsonb
WHERE reasoning::text LIKE '%??%';
