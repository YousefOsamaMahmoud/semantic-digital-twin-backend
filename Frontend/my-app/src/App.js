import { useState } from "react";
import Layout        from "./components/layout/Layout";
import Login         from "./pages/Login";
import Dashboard     from "./pages/Dashboard";
import SLAUpload     from "./pages/SLAUpload";
import InventoryRisk from "./pages/InventoryRisk";
import Suppliers     from "./pages/Suppliers";
import SLAViolations from "./pages/SLAViolations";
import ChatAssistant from "./pages/ChatAssistant";
import Alerts        from "./pages/Alerts";
import { ROLE_HOME, ROLE_PAGES } from "./auth/roles";
import "./styles/dashboard.css";

export default function App() {
  const [user,          setUser]          = useState(null);
  const [activePage,    setActivePage]    = useState("dashboard");
  const [refreshKey,    setRefreshKey]    = useState(0);
  const [aiPrompt,      setAiPrompt]      = useState("");
  const [initialAlertId, setInitialAlertId] = useState(null);
  const [notifVersion,  setNotifVersion]  = useState(0); // bumped when alerts are marked read

  const handleLogin    = (u) => { setUser(u); setActivePage(ROLE_HOME[u.role] || "dashboard"); };
  const handleLogout   = ()  => { setUser(null); setActivePage("dashboard"); };
  const handleNavigate = (page, data = null) => {
    if ((ROLE_PAGES[user?.role] || []).includes(page)) {
      setActivePage(page);
      if (page === "ai" && typeof data === "string") {
        setAiPrompt(data);
      }
      if (page === "alerts" && data?.alertId) {
        setInitialAlertId(data.alertId);
      } else if (page !== "alerts") {
        setInitialAlertId(null);
      }
    }
  };
  const handleRefresh     = () => setRefreshKey(k => k + 1);
  const bumpNotifVersion  = () => setNotifVersion(v => v + 1);

  if (!user) return <Login onLogin={handleLogin} />;

  const props = { user, onNavigate: handleNavigate };

  const renderPage = () => {
    switch (activePage) {
      case "dashboard":  return <Dashboard      {...props} />;
      case "sla":        return <SLAUpload      {...props} />;
      case "inventory":  return <InventoryRisk  {...props} />;
      case "suppliers":  return <Suppliers      {...props} />;
      case "violations": return <SLAViolations  {...props} />;
      case "ai":         return <ChatAssistant  {...props} initialPrompt={aiPrompt} clearInitialPrompt={() => setAiPrompt("")} />;
      case "alerts":     return <Alerts         {...props} initialAlertId={initialAlertId} clearInitialAlertId={() => setInitialAlertId(null)} onAlertsChanged={bumpNotifVersion} />;
      default:           return <Dashboard      {...props} />;
    }
  };

  return (
    <Layout activePage={activePage} onNavigate={handleNavigate} user={user} onLogout={handleLogout} onRefresh={handleRefresh} refreshKey={refreshKey} notifVersion={notifVersion} onAlertsChanged={bumpNotifVersion}>
      {renderPage()}
    </Layout>
  );
}
