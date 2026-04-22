/**
 * Staff Management Tab — Employee CRUD operations
 *
 * Features:
 *   - List all employees in the store
 *   - Create new employees with role assignment
 *   - Edit employee details and roles
 *   - Deactivate/reactivate employees
 *   - Force password reset for employees
 *   - Role-based access control (admin only)
 */

import { useState, useEffect } from "react";
import { employeesAPI } from "../api/client";
import { Section, shellStyles } from "../components/backoffice";

const ROLES = {
  cashier: "Cashier",
  supervisor: "Supervisor",
  manager: "Manager",
  admin: "Admin",
};

export default function StaffManagementTab() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  // Form state
  const [formData, setFormData] = useState({
    full_name: "",
    email: "",
    phone: "",
    role: "cashier",
    terminal_id: "",
    password: "",
    confirm_password: "",
  });

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    loadEmployees();
  }, []);

  const loadEmployees = async () => {
    try {
      setLoading(true);
      const response = await employeesAPI.listEmployees();
      setEmployees(response.employees || []);
    } catch (err) {
      setError(err.message || "Failed to load employees");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateEmployee = async (e) => {
    e.preventDefault();
    try {
      if (formData.password) {
        const hasUpper = /[A-Z]/.test(formData.password);
        const hasLower = /[a-z]/.test(formData.password);
        const hasDigit = /[0-9]/.test(formData.password);
        const hasSymbol = /[^A-Za-z0-9]/.test(formData.password);
        if (!(hasUpper && hasLower && hasDigit && hasSymbol)) {
          setError("Password must include uppercase, lowercase, number, and symbol.");
          return;
        }
      }
      if (formData.password !== formData.confirm_password) {
        setError("Password and confirm password do not match.");
        return;
      }
      const payload = { ...formData };
      delete payload.confirm_password;
      if (!payload.password) delete payload.password;
      const response = await employeesAPI.createEmployee(payload);
      if (response?.temporary_password) {
        alert(`Employee created with temporary password: ${response.temporary_password}`);
      }
      setFormData({
        full_name: "",
        email: "",
        phone: "",
        role: "cashier",
        terminal_id: "",
        password: "",
        confirm_password: "",
      });
      setShowCreateForm(false);
      loadEmployees();
    } catch (err) {
      setError(err.message || "Failed to create employee");
    }
  };

  const handleUpdateEmployee = async (e) => {
    e.preventDefault();
    try {
      await employeesAPI.updateEmployee(editingEmployee.id, formData);
      setEditingEmployee(null);
      setFormData({
        full_name: "",
        email: "",
        phone: "",
        role: "cashier",
        terminal_id: "",
        password: "",
        confirm_password: "",
      });
      loadEmployees();
    } catch (err) {
      setError(err.message || "Failed to update employee");
    }
  };

  const handleDeactivateEmployee = async (employeeId) => {
    if (!confirm("Are you sure you want to deactivate this employee?")) return;
    try {
      await employeesAPI.deactivateEmployee(employeeId);
      loadEmployees();
    } catch (err) {
      setError(err.message || "Failed to deactivate employee");
    }
  };

  const handleResetPassword = async (employeeId) => {
    if (!confirm("This will generate a new temporary password and force the employee to change it on next login. Continue?")) return;
    try {
      const response = await employeesAPI.resetPassword(employeeId);
      alert(response?.temporary_password
        ? `Password reset complete. Temporary password: ${response.temporary_password}`
        : "Password reset complete. Share the new temporary password with the employee through a secure channel.");
    } catch (err) {
      setError(err.message || "Failed to reset password");
    }
  };

  const startEdit = (employee) => {
    setEditingEmployee(employee);
    setFormData({
      full_name: employee.full_name,
      email: employee.email,
      phone: employee.phone || "",
      role: employee.role,
      terminal_id: employee.terminal_id || "",
    });
  };

  const cancelEdit = () => {
    setEditingEmployee(null);
    setFormData({
      full_name: "",
      email: "",
      phone: "",
      role: "cashier",
      terminal_id: "",
      password: "",
      confirm_password: "",
    });
  };

  if (loading) {
    return (
      <Section title="Staff Management">
        <div style={{ textAlign: "center", padding: "2rem" }}>Loading employees...</div>
      </Section>
    );
  }

  return (
    <div>
      <Section title="Staff Management">
        {error && (
          <div style={{
            backgroundColor: "#fee",
            color: "#c33",
            padding: "1rem",
            borderRadius: "4px",
            marginBottom: "1rem",
            border: "1px solid #fcc"
          }}>
            {error}
            <button
              onClick={() => setError(null)}
              style={{
                float: "right",
                background: "none",
                border: "none",
                color: "#c33",
                cursor: "pointer",
                fontSize: "1.2em"
              }}
            >
              ×
            </button>
          </div>
        )}

        <div style={{ marginBottom: "1rem" }}>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            style={{
              backgroundColor: "#007bff",
              color: "white",
              border: "none",
              padding: "0.5rem 1rem",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            {showCreateForm ? "Cancel" : "+ Add Employee"}
          </button>
        </div>

        {showCreateForm && (
          <div style={{
            backgroundColor: "#f8f9fa",
            padding: "1rem",
            borderRadius: "4px",
            marginBottom: "1rem",
            border: "1px solid #dee2e6"
          }}>
            <h3>Create New Employee</h3>
            <form onSubmit={handleCreateEmployee}>
              <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr" }}>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Full Name *
                  </label>
                  <input
                    type="text"
                    value={formData.full_name}
                    onChange={(e) => setFormData({...formData, full_name: e.target.value})}
                    required
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Email *
                  </label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                    required
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Phone
                  </label>
                  <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => setFormData({...formData, phone: e.target.value})}
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Role *
                  </label>
                  <select
                    value={formData.role}
                    onChange={(e) => setFormData({...formData, role: e.target.value})}
                    required
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  >
                    {Object.entries(ROLES).map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Terminal ID
                  </label>
                  <input
                    type="text"
                    value={formData.terminal_id}
                    onChange={(e) => setFormData({...formData, terminal_id: e.target.value})}
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Password
                  </label>
                  <input
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({...formData, password: e.target.value})}
                    placeholder="Optional: leave blank to auto-generate"
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                  <small style={{ color: "#6c757d" }}>
                    If provided: include uppercase, lowercase, number, and symbol.
                  </small>
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Confirm Password
                  </label>
                  <input
                    type="password"
                    value={formData.confirm_password}
                    onChange={(e) => setFormData({...formData, confirm_password: e.target.value})}
                    placeholder="Re-enter password"
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
              </div>
              <div style={{ marginTop: "1rem" }}>
                <button
                  type="submit"
                  style={{
                    backgroundColor: "#28a745",
                    color: "white",
                    border: "none",
                    padding: "0.5rem 1rem",
                    borderRadius: "4px",
                    cursor: "pointer",
                    marginRight: "0.5rem"
                  }}
                >
                  Create Employee
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  style={{
                    backgroundColor: "#6c757d",
                    color: "white",
                    border: "none",
                    padding: "0.5rem 1rem",
                    borderRadius: "4px",
                    cursor: "pointer"
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {editingEmployee && (
          <div style={{
            backgroundColor: "#fff3cd",
            padding: "1rem",
            borderRadius: "4px",
            marginBottom: "1rem",
            border: "1px solid #ffeaa7"
          }}>
            <h3>Edit Employee: {editingEmployee.full_name}</h3>
            <form onSubmit={handleUpdateEmployee}>
              <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr" }}>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Full Name *
                  </label>
                  <input
                    type="text"
                    value={formData.full_name}
                    onChange={(e) => setFormData({...formData, full_name: e.target.value})}
                    required
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Email *
                  </label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                    required
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Phone
                  </label>
                  <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => setFormData({...formData, phone: e.target.value})}
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Role *
                  </label>
                  <select
                    value={formData.role}
                    onChange={(e) => setFormData({...formData, role: e.target.value})}
                    required
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  >
                    {Object.entries(ROLES).map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "bold" }}>
                    Terminal ID
                  </label>
                  <input
                    type="text"
                    value={formData.terminal_id}
                    onChange={(e) => setFormData({...formData, terminal_id: e.target.value})}
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #ccc",
                      borderRadius: "4px",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
              </div>
              <div style={{ marginTop: "1rem" }}>
                <button
                  type="submit"
                  style={{
                    backgroundColor: "#28a745",
                    color: "white",
                    border: "none",
                    padding: "0.5rem 1rem",
                    borderRadius: "4px",
                    cursor: "pointer",
                    marginRight: "0.5rem"
                  }}
                >
                  Update Employee
                </button>
                <button
                  type="button"
                  onClick={cancelEdit}
                  style={{
                    backgroundColor: "#6c757d",
                    color: "white",
                    border: "none",
                    padding: "0.5rem 1rem",
                    borderRadius: "4px",
                    cursor: "pointer"
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        <div style={{
          backgroundColor: "white",
          borderRadius: "4px",
          border: "1px solid #dee2e6",
          overflowX: "auto"
        }}>
          <table style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: isMobile ? "0.8rem" : "0.9rem"
          }}>
            <thead>
              <tr style={{ backgroundColor: "#f8f9fa" }}>
                <th style={{ padding: "0.75rem", textAlign: "left", borderBottom: "1px solid #dee2e6", fontWeight: "bold" }}>Name</th>
                <th style={{ padding: "0.75rem", textAlign: "left", borderBottom: "1px solid #dee2e6", fontWeight: "bold" }}>Email</th>
                {!isMobile && <th style={{ padding: "0.75rem", textAlign: "left", borderBottom: "1px solid #dee2e6", fontWeight: "bold" }}>Phone</th>}
                <th style={{ padding: "0.75rem", textAlign: "left", borderBottom: "1px solid #dee2e6", fontWeight: "bold" }}>Role</th>
                {!isMobile && <th style={{ padding: "0.75rem", textAlign: "left", borderBottom: "1px solid #dee2e6", fontWeight: "bold" }}>Terminal</th>}
                <th style={{ padding: "0.75rem", textAlign: "left", borderBottom: "1px solid #dee2e6", fontWeight: "bold" }}>Status</th>
                <th style={{ padding: "0.75rem", textAlign: "center", borderBottom: "1px solid #dee2e6", fontWeight: "bold" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((employee) => (
                <tr key={employee.id} style={{ borderBottom: "1px solid #f1f3f4" }}>
                  <td style={{ padding: "0.75rem" }}>{employee.full_name}</td>
                  <td style={{ padding: "0.75rem" }}>{employee.email}</td>
                  {!isMobile && <td style={{ padding: "0.75rem" }}>{employee.phone || "-"}</td>}
                  <td style={{ padding: "0.75rem" }}>
                    <span style={{
                      backgroundColor: employee.role === "ADMIN" ? "#dc3545" :
                                       employee.role === "MANAGER" ? "#ffc107" :
                                       employee.role === "SUPERVISOR" ? "#17a2b8" : "#28a745",
                      color: "white",
                      padding: "0.25rem 0.5rem",
                      borderRadius: "12px",
                      fontSize: "0.75rem",
                      fontWeight: "bold"
                    }}>
                      {ROLES[employee.role] || employee.role}
                    </span>
                  </td>
                  {!isMobile && <td style={{ padding: "0.75rem" }}>{employee.terminal_id || "-"}</td>}
                  <td style={{ padding: "0.75rem" }}>
                    <span style={{
                      color: employee.is_active ? "#28a745" : "#dc3545",
                      fontWeight: "bold"
                    }}>
                      {employee.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td style={{ padding: "0.75rem", textAlign: "center" }}>
                    <div style={{ display: "flex", gap: "0.25rem", justifyContent: "center", flexWrap: "wrap" }}>
                      <button
                        onClick={() => startEdit(employee)}
                        style={{
                          backgroundColor: "#007bff",
                          color: "white",
                          border: "none",
                          padding: "0.25rem 0.5rem",
                          borderRadius: "3px",
                          cursor: "pointer",
                          fontSize: "0.75rem"
                        }}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleResetPassword(employee.id)}
                        style={{
                          backgroundColor: "#ffc107",
                          color: "black",
                          border: "none",
                          padding: "0.25rem 0.5rem",
                          borderRadius: "3px",
                          cursor: "pointer",
                          fontSize: "0.75rem"
                        }}
                      >
                        Reset PW
                      </button>
                      {employee.is_active ? (
                        <button
                          onClick={() => handleDeactivateEmployee(employee.id)}
                          style={{
                            backgroundColor: "#dc3545",
                            color: "white",
                            border: "none",
                            padding: "0.25rem 0.5rem",
                            borderRadius: "3px",
                            cursor: "pointer",
                            fontSize: "0.75rem"
                          }}
                        >
                          Deactivate
                        </button>
                      ) : (
                        <button
                          onClick={() => handleDeactivateEmployee(employee.id)}
                          style={{
                            backgroundColor: "#28a745",
                            color: "white",
                            border: "none",
                            padding: "0.25rem 0.5rem",
                            borderRadius: "3px",
                            cursor: "pointer",
                            fontSize: "0.75rem"
                          }}
                        >
                          Reactivate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {employees.length === 0 && (
                <tr>
                  <td colSpan={isMobile ? 5 : 7} style={{ padding: "2rem", textAlign: "center", color: "#6c757d" }}>
                    No employees found. Create your first employee to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}