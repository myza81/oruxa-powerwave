// Runtime configuration for the Powerwave frontend.
//
// This checked-in file is the default used when serving the frontend directly
// from a developer machine (no Docker). In a container it is regenerated at
// startup from the API_BASE_URL/ENVIRONMENT/APP_VERSION environment
// variables (see frontend/docker-entrypoint.d/10-powerwave-config.sh), so
// the same image can be promoted from DEV to PROD without a rebuild.
// buildVersion is "local" here deliberately -- a bare file-serve/no-Docker
// session never has a real deployed Git SHA, and this must never fabricate
// one (see docs/project-memory/MIGRATION_PLAN.md's Phase 4A-UAT3 record).
window.POWERWAVE_CONFIG = {
  apiBaseUrl: "http://127.0.0.1:8000",
  environment: "development",
  buildVersion: "local",
};
