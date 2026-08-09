// Runtime configuration for the Powerwave frontend.
//
// This checked-in file is the default used when serving the frontend directly
// from a developer machine (no Docker). In a container it is regenerated at
// startup from the API_BASE_URL environment variable, so the same image can be
// promoted from DEV to PROD without a rebuild.
window.POWERWAVE_CONFIG = {
  apiBaseUrl: "http://127.0.0.1:8000",
};
