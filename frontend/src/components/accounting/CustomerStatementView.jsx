import { useEffect, useState } from "react";
import { accountingAPI, customersAPI, fmtKES } from "../../api/client";

export default function CustomerStatementView() {
  const [customerId, setCustomerId] = useState("");
  const [customers, setCustomers] = useState([]);
  const [data, setData] = useState(null);

  useEffect(() => {
    customersAPI.list().then(r => setCustomers(r.items || r || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (customerId) accountingAPI.customerStatement(customerId).then(setData).catch(() => setData(null));
  }, [customerId]);

  return (
    <div>
      <select value={customerId} onChange={e => setCustomerId(e.target.value)}>
        <option value="">Select customer</option>
        {customers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      {data ? (
        <div>
          <div>Store Credit Wallet: {fmtKES(data.store_credit_balance)}</div>
          <table style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Ref</th>
                <th>Debit</th>
                <th>Credit</th>
                <th>AR Balance</th>
                <th>Wallet Δ</th>
                <th>Wallet Balance</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.date}</td>
                  <td>{r.type}</td>
                  <td>{r.reference}</td>
                  <td>{fmtKES(r.debit)}</td>
                  <td>{fmtKES(r.credit)}</td>
                  <td>{fmtKES(r.running_balance)}</td>
                  <td>{fmtKES(r.wallet_delta || 0)}</td>
                  <td>{fmtKES(r.wallet_running_balance || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div>Select customer to view statement</div>}
    </div>
  );
}
