const buttonStyle = (active, disabled) => ({
  padding: "6px 14px",
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: "0.04em",
  borderRadius: 8,
  cursor: disabled ? "default" : "pointer",
  border: "1px solid",
  borderColor: active ? "#3b4a68" : "transparent",
  background: active ? "#1b2540" : "transparent",
  color: disabled ? "#4f5a70" : active ? "#eaf0fb" : "#8a94a6",
  transition: "all .15s",
});

export default function ModeSwitcher({ mode, onChange }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 4,
        background: "#0f1524",
        padding: 4,
        borderRadius: 10,
        border: "1px solid #1a2338",
      }}
    >
      <button style={buttonStyle(mode === "geo", false)} onClick={() => onChange("geo")}>
        Geographic
      </button>
      <button style={buttonStyle(false, true)} disabled title="Coming soon">
        Schematic
      </button>
    </div>
  );
}
