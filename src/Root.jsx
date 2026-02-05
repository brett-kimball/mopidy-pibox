import React, { lazy } from "react";
import HomePage from "pages/HomePage";
import { Route, Switch, Redirect, useLocation } from "wouter";
import { startSession } from "services/mopidy.js";
import { AdminContext, useAdminContext } from "hooks/admin.js";
import { useConfig } from "hooks/config";
import { useSessionStarted } from "hooks/session";
import { LoadingScreen } from "components/common/LoadingScreen";
import { useConnected } from "hooks/connection";

const NewSessionPage = lazy(() => import("./pages/NewSessionPage.jsx"));
const SessionPage = lazy(() => import("./pages/SessionPage.jsx"));
const DisplayPage = lazy(() => import("./pages/DisplayPage.jsx"));
const ViewPage = lazy(() => import("./pages/ViewPage.jsx"));

const App = () => {
  const { sessionStarted, sessionStartedLoading, refetchSessionStarted } =
    useSessionStarted();
  const { configLoading, config } = useConfig();
  const connected = useConnected();

  const [location, navigate] = useLocation();

  const admin = useAdminContext();

  // Track the previous sessionStarted value
  const prevSessionStartedRef = React.useRef(sessionStarted);

  // When session ends, navigate to root to show NewSessionPage
  React.useEffect(() => {
    // If we had a session and now we don't, and we're not on /view
    if (
      prevSessionStartedRef.current === true &&
      sessionStarted === false &&
      location !== "/view"
    ) {
      // Navigate to root so the NewSessionPage is displayed
      navigate("/", { replace: true });
    }
    prevSessionStartedRef.current = sessionStarted;
  }, [sessionStarted, location, navigate]);

  const createSession = async ({
    votesToSkip,
    selectedPlaylists,
    automaticallyStartPlaying,
    enableShuffle,
  }) => {
    await startSession(
      votesToSkip,
      selectedPlaylists,
      automaticallyStartPlaying,
      enableShuffle,
    );
    refetchSessionStarted();
    navigate("/");
  };

  // If the kiosk is showing the dedicated /view page, never navigate away
  // from it — render the ViewPage regardless of session/connection state.
  if (location === "/view") {
    return (
      <BaseProviders admin={admin}>
        <ViewPage />
      </BaseProviders>
    );
  }

  if (!connected || sessionStartedLoading || configLoading) {
    const siteTitle = config?.siteTitle ?? "pibox";
    return (
      <div className="Root">
        <LoadingScreen siteTitle={siteTitle} />
      </div>
    );
  }

  if (!sessionStarted) {
    return (
      <BaseProviders admin={admin}>
        <NewSessionPage onStartSessionClick={createSession} />
      </BaseProviders>
    );
  }

  return (
    <BaseProviders admin={admin}>
      <Switch>
        <Route path="/session">
          {admin.isAdmin ? <SessionPage /> : <Redirect to="/" replace />}
        </Route>
        <Route path="/display">
          <DisplayPage />
        </Route>
        <Route path="/view">
          <ViewPage />
        </Route>
        <Route>
          <HomePage />
        </Route>
      </Switch>
    </BaseProviders>
  );
};

function BaseProviders({ children, admin }) {
  const { config } = useConfig();

  React.useEffect(() => {
    const title = config?.siteTitle ?? "pibox";
    if (typeof document !== "undefined") {
      document.title = title;
    }
  }, [config]);

  return (
    <AdminContext.Provider value={admin}>
      <div className="Root">{children}</div>
    </AdminContext.Provider>
  );
}

export default App;
