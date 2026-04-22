import { authAPI } from "../../api/client";

export const supervisorActions = {
  // Confirm supervisor authentication
  confirmSupervisorAction: async (supervisorEmail, supervisorPin, pendingAction) => {
    if (!supervisorEmail || !supervisorPin) {
      throw new Error("Supervisor email and password are required.");
    }

    try {
      const auth = await authAPI.login(supervisorEmail, supervisorPin);

      if (!["supervisor", "manager", "admin"].includes(auth.role)) {
        throw new Error("This account is not allowed to approve supervisor actions.");
      }

      return {
        authenticated: true,
        action: pendingAction,
        role: auth.role,
      };
    } catch (err) {
      throw new Error(err.message || "Supervisor authentication failed");
    }
  },

  // Handle approved supervisor action
  handleApprovedAction: (action, clearCartFn) => {
    if (action === "void") {
      clearCartFn?.();
      return true;
    }
    if (action === "return") {
      window.dispatchEvent(new CustomEvent("smartlynx:navigate", { detail: { page: "backoffice" } }));
      alert("Open Back Office → Transactions to create the return/refund request.");
      return true;
    }
    return false;
  },
};
