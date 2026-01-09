// This is your new central configuration file for the frontend.

// -----------------------------------------------------------------
// === CHOOSE YOUR ENVIRONMENT =====================================
// -----------------------------------------------------------------
// config.js - Universal Configuration
const getConfiguration = () => {
    const hostname = window.location.hostname;

    // 1. Local Development
    if (hostname === '127.0.0.1' || hostname === 'localhost') {
        return {
            API_BASE_URL: 'http://127.0.0.1:5000',
            SOCKET_URL: 'http://127.0.0.1:5000',
            environment: 'local'
        };
    }

    // 2. Vercel Deployment (Recommended for Frontend)
    if (hostname.includes('vercel.app')) {
        return {
            // Using a relative path '/api' works best if backend is on Vercel too
            API_BASE_URL: '/api', 
            SOCKET_URL: window.location.origin,
            environment: 'vercel'
        };
    }

    // 3. Render Deployment (or any other fallback)
    return {
        API_BASE_URL: 'https://esp32-datalogger.onrender.com',
        SOCKET_URL: 'https://esp32-datalogger.onrender.com',
        environment: 'production'
    };
};

// Create the global config object
const APP_CONFIG = getConfiguration();

// Ensure it is available globally for all other scripts
window.APP_CONFIG = APP_CONFIG;

console.log(`Running in ${APP_CONFIG.environment} mode. API URL: ${APP_CONFIG.API_BASE_URL}`);
