import { useState } from "react";

export function usePOSSupervisor() {
  const [showSupervisorModal, setShowSupervisorModal] = useState(false);
  const [supervisorEmail, setSupervisorEmail] = useState("");
  const [supervisorPin, setSupervisorPin] = useState("");
  const [supervisorLoading, setSupervisorLoading] = useState(false);
  const [pendingSupervisorAction, setPendingSupervisorAction] = useState(null);
  const [lockConfirm, setLockConfirm] = useState(false);

  const requestSupervisorApproval = (actionName) => {
    setPendingSupervisorAction(actionName);
    setSupervisorEmail("");
    setSupervisorPin("");
    setShowSupervisorModal(true);
  };

  const closeSupervisorModal = () => {
    setShowSupervisorModal(false);
    setPendingSupervisorAction(null);
    setSupervisorEmail("");
    setSupervisorPin("");
  };

  return {
    showSupervisorModal,
    setShowSupervisorModal,
    supervisorEmail,
    setSupervisorEmail,
    supervisorPin,
    setSupervisorPin,
    supervisorLoading,
    setSupervisorLoading,
    pendingSupervisorAction,
    setPendingSupervisorAction,
    lockConfirm,
    setLockConfirm,
    requestSupervisorApproval,
    closeSupervisorModal,
  };
}
