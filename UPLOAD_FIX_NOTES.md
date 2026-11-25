# Upload Fix Notes

## Chatbot crash and route error handling

- **Problem:** `Chatbot.jsx` rendered `<Helmet>` without importing it, which caused the chatbot page to throw at render time. Any route render error could also blank the app.
- **Verification:** Confirmed the missing import in `Chatbot.jsx`, checked that `main.jsx` already provides `HelmetProvider`, and ran the frontend build and lint before and after the changes. There is no frontend component-test setup in this project.
- **Fix:** Imported `Helmet` from `react-helmet-async` and wrapped the routes in a React error boundary. The boundary logs rendering errors and shows a friendly message with a Reload button.
