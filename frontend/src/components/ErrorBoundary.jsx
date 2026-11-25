import React, { Component } from 'react';

class ErrorBoundary extends Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('An error occurred while rendering the page:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="error-boundary" role="alert">
          <h1>Something went wrong</h1>
          <p>We could not load this page. Please reload and try again.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </section>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
