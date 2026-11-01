import { defineConfig } from 'orval';

export default defineConfig({
  radar: {
    // Offline export of /api/v1/openapi.json.
    input: './openapi.json',
    output: {
      target: './src/api/generated.ts',
      client: 'react-query',
      httpClient: 'fetch',
      mock: true,
      clean: false,
      override: {
        fetch: {
          includeHttpResponseReturnType: false,
          forceSuccessResponse: true,
        },
        mutator: {
          path: './src/api/http.ts',
          name: 'apiFetch',
        },
      },
    },
  },
});