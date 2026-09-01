import styled from "styled-components";
import { Link, NavLink, Outlet } from "react-router-dom";

const Header = styled.header`
  background: ${({ theme }) => theme.colors.surface};
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
`;

const HeaderInner = styled.div`
  max-width: 1280px;
  margin: 0 auto;
  padding: 14px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const Brand = styled(Link)`
  text-decoration: none;
  color: ${({ theme }) => theme.colors.ink};
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;

  span {
    font-family: ${({ theme }) => theme.fonts.mono};
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.14em;
    color: ${({ theme }) => theme.colors.primary};
    margin-left: 6px;
    vertical-align: 1px;
  }
`;

const Nav = styled.nav`
  display: flex;
  gap: 8px;

  a {
    text-decoration: none;
    font-size: 14px;
    font-weight: 550;
    color: ${({ theme }) => theme.colors.ink2};
    padding: 6px 12px;
    border-radius: ${({ theme }) => theme.borderRadius.sm};

    &:hover {
      color: ${({ theme }) => theme.colors.primary};
    }
    &.active {
      color: ${({ theme }) => theme.colors.primary};
      background: ${({ theme }) => theme.colors.primaryTint};
    }
  }
`;

const Main = styled.main`
  min-height: calc(100vh - 57px);
`;

export const PageBody = styled.div`
  max-width: 1280px;
  margin: 0 auto;
  padding: 28px 32px 64px;
`;

const Layout = () => (
  <>
    <Header>
      <HeaderInner>
        <Brand to="/">
          FAIRSCAPE<span>LITE</span>
        </Brand>
        <Nav>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/search">Search</NavLink>
        </Nav>
      </HeaderInner>
    </Header>
    <Main>
      <Outlet />
    </Main>
  </>
);

export default Layout;
