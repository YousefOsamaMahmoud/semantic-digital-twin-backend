import { C } from "../../styles/theme";
import Sidebar from "./Sidebar";
import Topbar  from "./Topbar";

export default function Layout({ activePage, onNavigate, user, onLogout, children, onRefresh, refreshKey, notifVersion, onAlertsChanged }) {
  return (
    <div style={{
      display: "flex", height: "100vh", width: "100vw",
      background: C.bg, color: C.text,
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      overflow: "hidden", fontSize: 14,
    }}>
      <Sidebar activePage={activePage} onNavigate={onNavigate} user={user} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <Topbar activePage={activePage} onNavigate={onNavigate} user={user} onLogout={onLogout} onRefresh={onRefresh} notifVersion={notifVersion} onAlertsChanged={onAlertsChanged} />
        <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }} className="page-enter" key={`${activePage}-${refreshKey}`}>
          {children}
        </div>
      </div>
    </div>
  );
}
