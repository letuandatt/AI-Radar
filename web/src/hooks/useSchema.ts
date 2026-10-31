import { useGetUISchema, type SchemaField, type UISchema } from '../api/generated';

export function useSchema(kind: 'table' | 'filter' | 'detail') {
  return useGetUISchema(kind);
}

/** Ignore unsupported field/renderer combinations; never interpret schema as HTML/code. */
export function allowedFields(
  schema: UISchema,
  bindings: Record<string, string>,
): SchemaField[] {
  if (schema.version !== 1) return [];

  const seen = new Set<string>();

  return schema.fields.filter(field => {
    if (bindings[field.key] !== field.renderer || seen.has(field.key)) {
      return false;
    }

    seen.add(field.key);
    return true;
  });
}