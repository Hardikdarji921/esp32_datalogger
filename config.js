// This is your new central configuration file for the frontend.

// -----------------------------------------------------------------
// === CHOOSE YOUR ENVIRONMENT =====================================
// -----------------------------------------------------------------
// To run locally: set environment = 'local'
// To run on Render: set environment = 'production'
//
const environment = 'local'; // <-- EDIT THIS LINE
// -----------------------------------------------------------------

const configs = {
    local: {
        API_BASE_URL: 'http://127.0.0.1:5000',
        SOCKET_URL: 'http://127.0.0.1:5000'
    },
    production: {
        API_BASE_URL: 'https://esp32-datalogger.onrender.com',
        SOCKET_URL: 'https://esp32-datalogger.onrender.com'
    }
};

// This line automatically selects the correct URLs based on your choice above.
const APP_CONFIG = configs[environment];