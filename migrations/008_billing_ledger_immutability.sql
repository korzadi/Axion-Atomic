-- 008: impide modificar o truncar el libro de créditos.
-- Las correcciones deben expresarse mediante asientos compensatorios.
CREATE OR REPLACE FUNCTION billing_reject_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'billing_credit_ledger es append-only; registre un movimiento compensatorio';
END;
$$;

CREATE TRIGGER trg_billing_ledger_no_update_delete
    BEFORE UPDATE OR DELETE ON billing_credit_ledger
    FOR EACH ROW EXECUTE FUNCTION billing_reject_ledger_mutation();

CREATE TRIGGER trg_billing_ledger_no_truncate
    BEFORE TRUNCATE ON billing_credit_ledger
    FOR EACH STATEMENT EXECUTE FUNCTION billing_reject_ledger_mutation();
