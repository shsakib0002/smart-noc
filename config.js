// API Configuration
// This file determines which API endpoint to use based on environment

const API_CONFIG = {
    // Development (local testing)
    development: 'http://localhost:8000',
    
    // Production (Your new Render Backend)
    production: 'https://smart-noc.onrender.com', 
    
    // Auto-detect environment
    getBaseURL: function() {
        // 1. Priority: Check if user has manually set a URL (e.g., for Ngrok)
        const customUrl = localStorage.getItem('NOC_CUSTOM_API');
        if (customUrl) return customUrl;

        // 2. Priority: If we're on localhost, use development API
        if (window.location.hostname === 'localhost' || 
            window.location.hostname === '127.0.0.1' ||
            window.location.hostname === '') {
            return this.development;
        }
        
        // 3. Otherwise use production API (Render)
        return this.production;
    }
};

// Export for use in HTML
window.API_BASE = API_CONFIG.getBaseURL();
console.log("API Base URL set to:", window.API_BASE);
