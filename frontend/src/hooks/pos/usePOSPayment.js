import { useState, useCallback } from "react";
import { useMpesaSocket } from "../useMpesaSocket";

export function usePOSPayment(sessionTerminalId, receipt) {
  const [paymentMode, setPaymentMode] = useState(null);
  const [cashInput, setCashInput] = useState("");
  const [mpesaPhone, setMpesaPhone] = useState("07");
  const [mpesaStatus, setMpesaStatus] = useState(null);
  const [mpesaFailMsg, setMpesaFailMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const handlePaymentConfirmed = useCallback(
    (confirmedTxnNumber) => {
      if (confirmedTxnNumber === receipt?.txn_number) {
        setMpesaStatus("confirmed");
      }
    },
    [receipt]
  );

  const handlePaymentFailed = useCallback(
    (txnNumber, resultCode, message) => {
      if (txnNumber === receipt?.txn_number) {
        setMpesaStatus("failed");
        setMpesaFailMsg(message || `Payment failed (code ${resultCode})`);
      }
    },
    [receipt]
  );

  const { connected: wsConnected } = useMpesaSocket(
    sessionTerminalId,
    handlePaymentConfirmed,
    handlePaymentFailed
  );

  const resetPaymentState = () => {
    setPaymentMode(null);
    setCashInput("");
    setMpesaPhone("07");
    setMpesaStatus(null);
    setMpesaFailMsg("");
  };

  return {
    paymentMode,
    setPaymentMode,
    cashInput,
    setCashInput,
    mpesaPhone,
    setMpesaPhone,
    mpesaStatus,
    setMpesaStatus,
    mpesaFailMsg,
    setMpesaFailMsg,
    loading,
    setLoading,
    wsConnected,
    resetPaymentState,
  };
}
