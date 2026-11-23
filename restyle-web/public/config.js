// Runtime settings. In the Docker image this file is rewritten at start from the container's
// environment (APP_KEY), so one image serves any environment. In development VITE_APP_KEY is used.
window.RESTYLE_CONFIG = { appKey: "" };
