// API Configuration
// This file determines which API endpoint to use based on the environment

const API_CONFIG = {
    // Development (local testing)
    development: 'http://localhost:8000',
    
    // Production (Your new Render Backend)
    production: 'https://smart-noc.onrender.com', 
    
    // Auto-detect environment
    getBaseURL: function() {
        // If we're on localhost, use development API
        if (window.location.hostname === 'localhost' || 
            window.location.hostname === '127.0.0.1' ||
            window.location.hostname === '') {
            return this.development;
        }
        // Otherwise use production API (Render)
        return this.production;
    }
};

// Export for use in HTML
window.API_BASE = API_CONFIG.getBaseURL();
