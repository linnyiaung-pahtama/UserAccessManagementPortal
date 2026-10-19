import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth";
import Layout from "./components/Layout";
import AccessDeniedPage from "./pages/AccessDeniedPage";
import AppsPage from "./pages/AppsPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";
import RequestAccessPage from "./pages/RequestAccessPage";
import AccessRequestsPage from "./pages/admin/AccessRequestsPage";
import ApplicationDetailPage from "./pages/admin/ApplicationDetailPage";
import ApplicationsPage from "./pages/admin/ApplicationsPage";
import AuditPage from "./pages/admin/AuditPage";
import OverviewPage from "./pages/admin/OverviewPage";
import UserDetailPage from "./pages/admin/UserDetailPage";
import UsersPage from "./pages/admin/UsersPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/request-access" element={<RequestAccessPage />} />
      <Route path="/access-denied" element={<AccessDeniedPage />} />
      <Route path="/change-password" element={<ChangePasswordPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<AppsPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="admin" element={<RequireAuth admin><OverviewPage /></RequireAuth>} />
        <Route path="admin/users" element={<RequireAuth admin><UsersPage /></RequireAuth>} />
        <Route path="admin/users/:id" element={<RequireAuth admin><UserDetailPage /></RequireAuth>} />
        <Route path="admin/applications" element={<RequireAuth admin><ApplicationsPage /></RequireAuth>} />
        <Route path="admin/applications/:id" element={<RequireAuth admin><ApplicationDetailPage /></RequireAuth>} />
        <Route path="admin/access-requests" element={<RequireAuth admin><AccessRequestsPage /></RequireAuth>} />
        <Route path="admin/audit"element={<RequireAuth admin><AuditPage /></RequireAuth>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
