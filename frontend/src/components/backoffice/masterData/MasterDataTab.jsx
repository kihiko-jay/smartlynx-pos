import { useState, useEffect } from "react";
import ProductsManager from "./ProductsManager";
import CategoriesManager from "./CategoriesManager";
import SuppliersManager from "./SuppliersManager";
import CustomersManager from "./CustomersManager";
import { shellStyles } from "../styles";
import { Section } from "../UIComponents";

const TABS = [
  { label: "Products", key: "products" },
  { label: "Categories", key: "categories" },
  { label: "Suppliers", key: "suppliers" },
  { label: "Customers", key: "customers" },
];

export default function MasterDataTab() {
  const [activeTab, setActiveTab] = useState("products");
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const renderTab = () => {
    switch (activeTab) {
      case "products": return <ProductsManager />;
      case "categories": return <CategoriesManager />;
      case "suppliers": return <SuppliersManager />;
      case "customers": return <CustomersManager />;
      default: return <ProductsManager />;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Tab Navigation */}
      <Section>
        <div style={{ display: "flex", gap: isMobile ? 4 : 8, overflowX: "auto", paddingBottom: 2, padding: isMobile ? "12px 12px" : "16px 16px" }}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={shellStyles.tabButton(activeTab === tab.key, isMobile)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </Section>

      {/* Tab Content */}
      {renderTab()}
    </div>
  );
}
