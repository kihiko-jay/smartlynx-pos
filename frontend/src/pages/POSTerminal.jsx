import { useEffect, useRef, useCallback, useState } from "react";
import {
  authAPI,
  sessionHelpers,
  clearSession,
} from "../api/client";
import { useOfflineQueue } from "../hooks/useOfflineQueue";
import {
  usePOSSession,
  usePOSCart,
  usePOSEntry,
  usePOSPayment,
  usePOSReceipts,
  usePOSHolds,
  usePOSSupervisor,
} from "../hooks/pos";
import { useSaleReset } from "../hooks/pos/useSaleReset";
import TitleBar from "../components/TitleBar";
import {
  EntryLookup,
  SessionOverview,
  CartTable,
  TotalsDisplay,
  SaleActions,
  PaymentSection,
  NumericKeypad,
  SaleCompletion,
  HeldSalesModal,
  ItemNotFoundModal,
  LockConfirmModal,
  SupervisorModal,
  SecureLoginModal,
  ProductSearchModal,
  PaymentModal,
  CashSessionOpenModal,
  CashSessionCloseModal,
} from "../components/pos";
import { pricingService } from "../services/pricingService";
import { transactionService } from "../services/transactionService";
import {
  cartActions,
  supervisorActions,
  entryActions,
  paymentFlow,
  receiptFlow,
  setupKeyboardShortcuts,
} from "../modules/pos";
const isElectron =
  typeof window !== "undefined" && !!window.electron?.app?.isElectron;

export default function POSTerminal({ onNavigate }) {
  const session = usePOSSession();
  const cart = usePOSCart();
  const entry = usePOSEntry();
  const receipts = usePOSReceipts();
  const payment = usePOSPayment(session.session?.terminal_id, receipts.receipt);
  const holds = usePOSHolds();
  const supervisor = usePOSSupervisor();

  const { isOnline, queueLength, enqueue, syncQueue } = useOfflineQueue();

  const entryRef = useRef(null);
  const restoreFocusRef = useRef(null);
  const txnKeyRef = useRef(null);
  const txnStateRef = useRef({ isActive: false, startTime: null });
  const autoResetTimeoutRef = useRef(null);

  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showNotFoundModal, setShowNotFoundModal] = useState(false);
  const [notFoundItemCode, setNotFoundItemCode] = useState("");
  const [pendingDeleteItemId, setPendingDeleteItemId] = useState(null);
  const [showOpenCashSessionModal, setShowOpenCashSessionModal] = useState(false);
  const [showCloseCashSessionModal, setShowCloseCashSessionModal] = useState(false);
  const [cashSessionLoading, setCashSessionLoading] = useState(false);
  const [cashSessionError, setCashSessionError] = useState("");

  const resetSaleState = useSaleReset({
    txnStateRef,
    txnKeyRef,
    cart,
    payment,
    receipts,
    entry,
    entryRef,
  });

  const totals = pricingService.calculateTotals(cart.cart);

  // Wrapped removeItem that requests supervisor approval
  const handleRemoveItemWithConfirm = useCallback((itemId) => {
    const item = cart.cart.find(i => i.id === itemId);
    if (!item) return;
    
    setPendingDeleteItemId(itemId);
    supervisor.requestSupervisorApproval("delete-item");
  }, [cart.cart, supervisor]);

  const handleCompleteSale = useCallback(async () => {
    if (payment.loading) return;

    if (payment.paymentMode === "cash") {
      const validation = paymentFlow.validateCashPayment(
        parseFloat(payment.cashInput) || 0,
        totals.total
      );
      if (!validation.valid) {
        entry.setError(validation.error);
        return;
      }
    }

    if (!payment.paymentMode) {
      entry.setError("Select a payment method.");
      return;
    }

    if (payment.paymentMode === "mpesa" && !payment.mpesaPhone?.trim()) {
      entry.setError("Enter M-Pesa phone number.");
      return;
    }

    if (payment.paymentMode === "credit" && !session.session?.customer_id) {
      entry.setError("Credit sales require a selected customer.");
      return;
    }

    if (payment.paymentMode === "store_credit" && !session.session?.customer_id) {
      entry.setError("Store credit payments require a selected customer.");
      return;
    }

    payment.setLoading(true);
    entry.setError("");

    if (!txnKeyRef.current) {
      txnKeyRef.current = transactionService.generateTxnNumber();
      txnStateRef.current = { isActive: true, startTime: Date.now() };
    }

    const idempotencyKey = txnKeyRef.current;

    const payload = transactionService.buildTransactionPayload(
      cart.cart,
      session.session?.terminal_id || "T01",
      payment.paymentMode,
      parseFloat(payment.cashInput) || 0,
      payment.mpesaPhone,
      {
        customerId: ["credit", "store_credit"].includes(payment.paymentMode) ? session.session?.customer_id || null : null,
        cashSessionId: payment.paymentMode === "cash" ? session.currentCashSession?.id || null : null,
        discountAmount: cart.cart.reduce((sum, item) => sum + Number(item.discount || 0), 0),
      }
    );

    try {
      let txn;

      if (!isOnline) {
        await enqueue({ ...payload, offline_txn_number: idempotencyKey });
        txn = transactionService.buildOfflineReceipt(
          idempotencyKey,
          cart.cart,
          { mode: payment.paymentMode },
          totals
        );
        receipts.setReceipt(txn);
        receipts.saveLastReceipt(txn);
        setShowPaymentModal(false);
        return;
      }

      if (payment.paymentMode === "mpesa" && !receipts.receipt) {
        txn = await transactionService.createTransaction(payload, idempotencyKey, {
          enqueue,
          isOnline,
        });

        receipts.setReceipt(txn);
        receipts.saveLastReceipt(txn);

        await transactionService.pushMpesaPrompt(
          payment.mpesaPhone,
          totals.total,
          idempotencyKey
        );

        payment.setMpesaStatus("waiting");
        setShowPaymentModal(false);
        return;
      }

      txn = await transactionService.createTransaction(payload, idempotencyKey, {
        enqueue,
        isOnline,
      });

      receipts.setReceipt(txn);
      receipts.saveLastReceipt(txn);
      setShowPaymentModal(false);
    } catch (e) {
      entry.setError(e.message);
      if (payment.paymentMode === "mpesa") {
        payment.setMpesaStatus("failed");
        payment.setMpesaFailMsg(e.message || "M-Pesa initiation failed");
      }
    } finally {
      payment.setLoading(false);
    }
  }, [
    payment,
    entry,
    totals,
    cart.cart,
    session.session?.terminal_id,
    receipts,
    enqueue,
    isOnline,
  ]);

  const openPaymentModal = useCallback(() => {
  if (payment.loading) return;

  const role = session.session?.role?.toLowerCase?.();
  const requiresCashSession = role === "cashier";

  if (requiresCashSession && !session.currentCashSession) {
    entry.setError("Open a cash session before selling.");
    setShowOpenCashSessionModal(true);
    return;
  }

  if (cart.cart.length === 0) {
    entry.setError("Cart is empty. Add items before payment.");
    return;
  }

  if (totals.total <= 0) {
    entry.setError("Order total must be greater than zero.");
    return;
  }

  restoreFocusRef.current =
    document.activeElement instanceof HTMLElement
      ? document.activeElement
      : entryRef.current;

  if (!payment.paymentMode) {
    payment.setPaymentMode("cash");
  }

  setShowPaymentModal(true);
  entry.setError("");
}, [
  payment,
  cart.cart.length,
  totals.total,
  entry,
  session.session?.role,
  session.currentCashSession,
]);

  const handlePaymentModalClose = () => {
    if (payment.loading) return;
    setShowPaymentModal(false);
  };

  const handlePaymentModalConfirm = async () => {
    await handleCompleteSale();
  };

  // Auto-open cash session modal if no active session after login
 useEffect(() => {
  const role = session.session?.role?.toLowerCase?.();

  const shouldForceCashSession =
    role === "cashier";

  if (
    session.session &&
    session.cashSessionsLoaded &&
    shouldForceCashSession &&
    !session.currentCashSession
  ) {
    setShowOpenCashSessionModal(true);
  }
}, [
  session.session,
  session.cashSessionsLoaded,
  session.currentCashSession,
]);

  const handleOpenCashSession = async (data) => {
    setCashSessionLoading(true);
    setCashSessionError("");
    try {
      const terminalId = data.terminal_id || session.session?.terminal_id || "T01";
      const newSession = await session.openCashSession(
        terminalId,
        data.opening_float,
        data.notes
      );
      // Ensure state is updated before closing modal
      session.setCurrentCashSession(newSession);
      setShowOpenCashSessionModal(false);
      setCashSessionError("");
      entry.setError("");
    } catch (err) {
      setCashSessionError(err.message || "Failed to open cash session");
    } finally {
      setCashSessionLoading(false);
    }
  };

  const handleCloseCashSession = async (data) => {
    setCashSessionLoading(true);
    setCashSessionError("");
    try {
      await session.closeCashSession(data.counted_cash, data.notes);
      // Clear current session after closing
      session.setCurrentCashSession(null);
      setShowCloseCashSessionModal(false);
      setCashSessionError("");
      entry.setError("");
    } catch (err) {
      setCashSessionError(err.message || "Failed to close cash session");
    } finally {
      setCashSessionLoading(false);
    }
  };

  useEffect(() => {
    return setupKeyboardShortcuts({
      onF2: (prefill) => entry.openSearch(prefill),
      onF9: openPaymentModal,
      onEscape: cart.clearCart,
      cart: cart.cart,
      receipt: receipts.receipt,
      total: totals.total,
      loading: payment.loading,
      modalOpen: showPaymentModal,
    });
  }, [
    entry,
    cart,
    receipts.receipt,
    totals.total,
    payment.loading,
    openPaymentModal,
    showPaymentModal,
  ]);

  useEffect(() => {
    if (isOnline && queueLength > 0) syncQueue();
  }, [isOnline, queueLength, syncQueue]);

  useEffect(() => {
    if (payment.paymentMode && (payment.cashInput || payment.mpesaPhone)) return;
    if (entry.showSearch) return;
    if (entryRef.current && document.activeElement === entryRef.current) return;
    if (entry.entryInput.trim().length > 0) return;

    if (entryRef.current) {
      entryRef.current.focus();
    }
  }, [
    entry.showSearch,
    receipts.receipt,
    entry.entryInput,
    payment.paymentMode,
    payment.cashInput,
    payment.mpesaPhone,
  ]);

  useEffect(() => {
    if (receipts.receipt) {
      setShowPaymentModal(false);

      if (autoResetTimeoutRef.current) {
        clearTimeout(autoResetTimeoutRef.current);
      }

      autoResetTimeoutRef.current = setTimeout(() => {
        resetSaleState();
      }, 5000);

      return () => {
        if (autoResetTimeoutRef.current) {
          clearTimeout(autoResetTimeoutRef.current);
        }
      };
    }
  }, [receipts.receipt, resetSaleState]);

  const handleSecureLogin = async (e) => {
    e.preventDefault();
    session.setSecureError("");
    session.setSecureLoading(true);

    try {
      const data = await authAPI.login(session.secureEmail, session.securePassword);

      await sessionHelpers.saveTokens({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
      });

      const nextSession = {
        id: data.employee_id,
        name: data.full_name,
        role: data.role,
        terminal_id: data.terminal_id,
        store_name: data.store_name,
        store_location: data.store_location,
      };

      sessionStorage.setItem("dukapos_session", JSON.stringify(nextSession));

      if (isElectron) {
        await session.saveSessionToElectron(nextSession);
      }

      session.setSession(nextSession);
      supervisor.setLockConfirm(false);
      session.closeSecureLogin();
      entry.setError("");
    } catch (err) {
      session.setSecureError(err.message || "Authentication failed");
    } finally {
      session.setSecureLoading(false);
    }
  };

  const handleSignout = async () => {
    try {
      const tokens = await sessionHelpers.getTokens();
      if (tokens.refreshToken) {
        try {
          await authAPI.logout(tokens.refreshToken);
        } catch (err) {
          console.warn("Failed to revoke token server-side:", err.message);
        }
      }

      await clearSession();
      if (onNavigate) onNavigate("login");
    } catch (err) {
      console.error("Signout error:", err);
      await clearSession();
      if (onNavigate) onNavigate("login");
    }
  };

  const handleItemNotFound = (itemCode) => {
    setNotFoundItemCode(itemCode);
    setShowNotFoundModal(true);
  };

  const handleEntryKeyDown = async (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();

    const val = entry.entryInput.trim();
    if (!val) return;

    entry.setEntryLoading(true);
    try {
      await entryActions.handleEntrySubmit(
        val,
        cart.addProductToCart,
        handleItemNotFound
      );
      entry.setEntryInput("");
    } catch (err) {
      entry.setError(err.message);
    } finally {
      entry.setEntryLoading(false);
    }
  };

  const handleSearchKeyDown = (e) => {
    entryActions.handleSearchNavigation(
      e,
      entry.searchResults,
      entry.searchIdx,
      entry.setSearchIdx,
      cart.addProductToCart,
      entry.closeSearch
    );
  };

  const handleSupervisorConfirm = async () => {
    supervisor.setSupervisorLoading(true);
    try {
      const result = await supervisorActions.confirmSupervisorAction(
        supervisor.supervisorEmail,
        supervisor.supervisorPin,
        supervisor.pendingSupervisorAction
      );

      // Handle delete-item action first, then other actions
      if (result.action === "delete-item" && pendingDeleteItemId) {
        cart.removeItem(pendingDeleteItemId);
        setPendingDeleteItemId(null);
      } else {
        supervisorActions.handleApprovedAction(result.action, cart.clearCart);
      }
      supervisor.closeSupervisorModal();
    } catch (err) {
      entry.setError(err.message);
    } finally {
      supervisor.setSupervisorLoading(false);
    }
  };

  const handleCreateHold = () => {
    try {
      const hold = cartActions.createHold(
        cart.cart,
        payment.paymentMode,
        payment.cashInput,
        payment.mpesaPhone,
        totals.subtotalExclusive,
        totals.vatAmount,
        totals.total
      );

      cartActions.saveHold(
        hold,
        holds.heldSales,
        holds.saveHeldSales,
        () => {
          cart.clearCart();
          payment.resetPaymentState();
          receipts.clearReceipt();
        }
      );

      entry.setError("");
    } catch (err) {
      entry.setError(err.message);
    }
  };

  const handleRecallHold = (holdId) => {
    cartActions.recallHold(
      holdId,
      holds.heldSales,
      holds.saveHeldSales,
      cart.setCart,
      cart.setSelectedCartId,
      payment.setPaymentMode,
      payment.setCashInput,
      payment.setMpesaPhone
    );

    holds.setShowHoldList(false);
    setTimeout(() => entryRef.current?.focus(), 50);
  };

  const canComplete = paymentFlow.canCompleteSale(
    cart.cart,
    payment.paymentMode,
    payment.cashInput,
    payment.mpesaStatus,
    payment.loading,
    totals.total,
    session.currentCashSession
  );

  return (
    <div
      style={{
        fontFamily: "Tahoma, Verdana, Arial, sans-serif",
        background: "#d7dee8",
        color: "#111827",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <style>{`
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-thumb { background: #9fb3d6; border-radius: 10px; }
        .rms-panel {
          background: linear-gradient(180deg, #f6f8fb 0%, #edf2f8 100%);
          border: 1px solid #9eb2ce;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.75);
        }
        .rms-title {
          background: linear-gradient(180deg, #155eef 0%, #003eb3 100%);
          color: #fff;
          font-weight: 700;
          letter-spacing: .03em;
          padding: 8px 12px;
          border-bottom: 1px solid #0b3186;
          text-transform: uppercase;
          font-size: 12px;
        }
        .rms-input {
          width: 100%;
          border: 1px solid #92a8c9;
          background: #fff;
          border-radius: 4px;
          padding: 10px 12px;
          font-size: 15px;
          outline: none;
        }
        .rms-input:focus { border-color: #155eef; box-shadow: 0 0 0 2px rgba(21,94,239,.12); }
      `}</style>

      <TitleBar
        session={session.session}
        isOnline={isOnline}
        queueLength={queueLength}
        wsConnected={payment.wsConnected}
      />

      <div
        style={{
          background: "linear-gradient(180deg, #0d58d2 0%, #04389c 100%)",
          color: "#fff",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 16px",
          borderBottom: "2px solid #022b76",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
          <div style={{ fontWeight: 800, fontSize: 20 }}>Store Operations POS</div>
          <div style={{ opacity: 0.9, fontSize: 13 }}>Smartlynx Unlimited</div>
          <div style={{ opacity: 0.9, fontSize: 13 }}>
            Terminal: {session.session?.terminal_id || "T01"}
          </div>
        </div>

        <div style={{ display: "flex", gap: 14, fontSize: 12, alignItems: "center" }}>
          <span>{session.session?.name || "Cashier"}</span>
          <span>{new Date().toLocaleString("en-KE")}</span>

          {session.currentCashSession ? (
            <button
              onClick={() => setShowCloseCashSessionModal(true)}
              style={{
                minHeight: 34,
                padding: "0 12px",
                cursor: "pointer",
                background: "#059669",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                fontWeight: "600",
                fontSize: "12px",
              }}
              title="Close the current shift"
            >
              Close Shift
            </button>
          ) : (
            <button
              onClick={() => setShowOpenCashSessionModal(true)}
              style={{
                minHeight: 34,
                padding: "0 12px",
                cursor: "pointer",
                background: "#f59e0b",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                fontWeight: "600",
                fontSize: "12px",
              }}
              title="Open a shift to start selling"
            >
              Open Shift
            </button>
          )}

          {(session.session?.role === "manager" ||
            session.session?.role === "admin") && (
            <button
              onClick={() => onNavigate?.("backoffice")}
              style={{ minHeight: 34, padding: "0 12px", cursor: "pointer" }}
            >
              Back Office
            </button>
          )}

          <button
            onClick={handleSignout}
            style={{
              minHeight: 34,
              padding: "0 12px",
              cursor: "pointer",
              background: "#ff4444",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              fontWeight: "600",
            }}
          >
            Sign Out
          </button>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 310px",
          gap: 10,
          padding: 10,
          flex: 1,
          minHeight: 0,
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateRows: "auto auto 1fr auto",
            gap: 10,
            minHeight: 0,
          }}
        >
          <EntryLookup
            entryInput={entry.entryInput}
            setEntryInput={entry.setEntryInput}
            entryLoading={entry.entryLoading}
            handleEntryKeyDown={handleEntryKeyDown}
            openSearch={entry.openSearch}
            clearEntry={() => entry.setEntryInput("")}
            entryRef={entryRef}
          />

          <SessionOverview
            session={session.session}
            currentCashSession={session.currentCashSession}
            cart={cart.cart}
            isOnline={isOnline}
          />

          <CartTable
            cart={cart.cart}
            selectedCartId={cart.selectedCartId}
            setSelectedCartId={cart.setSelectedCartId}
            editingQtyId={cart.editingQtyId}
            setEditingQtyId={cart.setEditingQtyId}
            handleQtyChange={cart.handleQtyChange}
            removeItem={handleRemoveItemWithConfirm}
          />

          <TotalsDisplay
            subtotalExVat={totals.subtotalExclusive}
            vatAmount={totals.vatAmount}
            total={totals.total}
          />
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateRows: "auto auto 1fr auto",
            gap: 10,
            minHeight: 0,
          }}
        >
          <SaleActions
            cart={cart.cart}
            heldSales={holds.heldSales}
            setShowHoldList={holds.setShowHoldList}
            requestSupervisorApproval={supervisor.requestSupervisorApproval}
            setLockConfirm={supervisor.setLockConfirm}
            lastReceipt={receipts.lastReceipt}
            handleReprintLastReceipt={() =>
              receipts.lastReceipt &&
              receiptFlow.printReceipt(
                receipts.lastReceipt,
                session.session?.store_name,
                session.session?.store_location
              )
            }
            createHold={handleCreateHold}
          />

          <PaymentSection
            paymentMode={payment.paymentMode}
            total={totals.total}
            receipt={receipts.receipt}
            mpesaStatus={payment.mpesaStatus}
            mpesaFailMsg={payment.mpesaFailMsg}
          />

          <NumericKeypad
            appendEntryDigit={entry.appendEntryDigit}
            backspaceEntry={entry.backspaceEntry}
            showSearch={entry.showSearch}
            closeSearch={entry.closeSearch}
            clearEntry={() => entry.setEntryInput("")}
            handleEntryKeyDown={handleEntryKeyDown}
            searchResults={entry.searchResults}
            searchIdx={entry.searchIdx}
            addProductToCart={cart.addProductToCart}
            closeSearchProp={entry.closeSearch}
          />

          <SaleCompletion
            error={entry.error}
            receipt={receipts.receipt}
            loading={payment.loading}
            canComplete={canComplete}
            handleCompleteSale={openPaymentModal}
            handlePrintReceipt={() =>
              receiptFlow.printReceipt(
                receipts.receipt,
                session.session?.store_name,
                session.session?.store_location
              )
            }
            handleWhatsAppReceipt={() =>
              receiptFlow.shareViaWhatsApp(
                receipts.receipt,
                session.session?.store_name
              )
            }
            clearCart={() => {
              resetSaleState();
            }}
          />
          {!session.currentCashSession && (
            <div
              style={{
                padding: "12px",
                background: "#fef3c7",
                border: "1px solid #fcd34d",
                borderRadius: "4px",
                color: "#92400e",
                fontSize: "13px",
                textAlign: "center",
                fontWeight: 600,
              }}
            >
              ⚠️ Shift not open. Click "Open Shift" above to begin selling.
            </div>
          )}
        </div>
      </div>

      <HeldSalesModal
        showHoldList={holds.showHoldList}
        setShowHoldList={holds.setShowHoldList}
        heldSales={holds.heldSales}
        recallHold={handleRecallHold}
      />

      <LockConfirmModal
        lockConfirm={supervisor.lockConfirm}
        setLockConfirm={supervisor.setLockConfirm}
        openSecureLogin={session.openSecureLogin}
      />

      <SupervisorModal
        showSupervisorModal={supervisor.showSupervisorModal}
        setShowSupervisorModal={supervisor.setShowSupervisorModal}
        pendingSupervisorAction={supervisor.pendingSupervisorAction}
        supervisorEmail={supervisor.supervisorEmail}
        setSupervisorEmail={supervisor.setSupervisorEmail}
        supervisorPin={supervisor.supervisorPin}
        setSupervisorPin={supervisor.setSupervisorPin}
        confirmSupervisorAction={handleSupervisorConfirm}
        supervisorLoading={supervisor.supervisorLoading}
      />

      <SecureLoginModal
        showSecureLogin={session.showSecureLogin}
        closeSecureLogin={session.closeSecureLogin}
        secureEmail={session.secureEmail}
        setSecureEmail={session.setSecureEmail}
        securePassword={session.securePassword}
        setSecurePassword={session.setSecurePassword}
        secureError={session.secureError}
        handleSecureLogin={handleSecureLogin}
        secureLoading={session.secureLoading}
        clearSession={clearSession}
        onNavigate={onNavigate}
      />

      <ProductSearchModal
        showSearch={entry.showSearch}
        closeSearch={entry.closeSearch}
        searchQuery={entry.searchQuery}
        setSearchQuery={entry.setSearchQuery}
        handleSearchKeyDown={handleSearchKeyDown}
        searchLoading={entry.searchLoading}
        searchResults={entry.searchResults}
        searchIdx={entry.searchIdx}
        setSearchIdx={entry.setSearchIdx}
        addProductToCart={cart.addProductToCart}
      />

      <PaymentModal
        open={showPaymentModal}
        total={totals.total}
        paymentMode={payment.paymentMode}
        setPaymentMode={(mode) => {
          payment.setPaymentMode(mode);
          payment.setMpesaStatus(null);
          payment.setMpesaFailMsg("");
        }}
        cashInput={payment.cashInput}
        setCashInput={payment.setCashInput}
        mpesaPhone={payment.mpesaPhone}
        setMpesaPhone={payment.setMpesaPhone}
        loading={payment.loading}
        canConfirm={canComplete}
        error={entry.error}
        onClose={handlePaymentModalClose}
        onConfirm={handlePaymentModalConfirm}
        restoreFocusRef={restoreFocusRef}
      />

      <ItemNotFoundModal
        show={showNotFoundModal}
        itemCode={notFoundItemCode}
        onClose={() => {
          setShowNotFoundModal(false);
          setNotFoundItemCode("");
        }}
        onSearch={() => {
          entry.openSearch(notFoundItemCode);
        }}
      />

      <CashSessionOpenModal
        isOpen={showOpenCashSessionModal}
        onSubmit={handleOpenCashSession}
        onClose={() => setShowOpenCashSessionModal(false)}
        loading={cashSessionLoading}
        error={cashSessionError}
        defaultTerminalId={session.session?.terminal_id}
        isMandatory={!session.currentCashSession}
      />

      <CashSessionCloseModal
        isOpen={showCloseCashSessionModal}
        session={session.currentCashSession}
        onSubmit={handleCloseCashSession}
        onClose={() => setShowCloseCashSessionModal(false)}
        loading={cashSessionLoading}
        error={cashSessionError}
      />
    </div>
  );
}